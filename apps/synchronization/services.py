"""
Motor de sincronización offline.

En lugar de duplicar reglas de negocio, cada operación se ejecuta a través de los
ViewSets existentes (serializers, perform_create, validaciones de bloqueo, acciones
como close/cancel/reactivate). Así una jornada registrada sin conexión pasa por
exactamente las mismas validaciones que una registrada en línea.
"""
import copy
import uuid

from django.db import IntegrityError, transaction
from django.utils.dateparse import parse_datetime
from rest_framework import status as http
from rest_framework.exceptions import APIException, ValidationError
from django.http import Http404

from apps.farms.views import FarmView, LotView
from apps.finance.views import OperatingExpenseViewSet
from apps.labor.views import (
    ActivityTypeViewSet,
    HarvestRecordViewSet,
    WorkdayDetailViewSet,
    WorkdayViewSet,
    WorkdayWorkerViewSet,
    WorkerViewSet,
)
from apps.payroll.views import (
    LaborPaymentViewSet,
    SettlementDetailHarvestViewSet,
    SettlementDetailWorkdayViewSet,
    SettlementViewSet,
)
from apps.production.views import SaleViewSet

from .models import SyncOperation

# Entidades que se pueden escribir sin conexión -> (ViewSet, acciones permitidas).
# Las acciones "custom" corresponden a métodos @action del ViewSet.
WRITABLE_ENTITIES = {
    "worker": (WorkerViewSet, {"create", "update"}),
    "workday": (WorkdayViewSet, {"create", "delete", "close", "update_labor"}),
    "workday_worker": (
        WorkdayWorkerViewSet,
        {"create", "update", "delete", "cancel", "reactivate"},
    ),
    "workday_detail": (WorkdayDetailViewSet, {"create", "update", "delete"}),
    "harvest_record": (HarvestRecordViewSet, {"create", "update", "cancel"}),
    "expense": (OperatingExpenseViewSet, {"create", "update"}),
    "sale": (SaleViewSet, {"create", "update"}),
}

# Datos que el dispositivo descarga para poder trabajar sin conexión.
SNAPSHOT_RESOURCES = {
    "farms": FarmView,
    "lots": LotView,
    "workers": WorkerViewSet,
    "activities": ActivityTypeViewSet,
    "workdays": WorkdayViewSet,
    "expenses": OperatingExpenseViewSet,
    "sales": SaleViewSet,
    "settlements": SettlementViewSet,
    "settlement_workdays": SettlementDetailWorkdayViewSet,
    "settlement_harvests": SettlementDetailHarvestViewSet,
    "payments": LaborPaymentViewSet,
}


def _build_view(viewset_class, request, action, data=None, pk=None):
    """Instancia un ViewSet como lo haría el router, con datos propios de la operación."""
    op_request = copy.copy(request)
    op_request._full_data = data if data is not None else {}
    view = viewset_class()
    view.request = op_request
    view.args = ()
    view.kwargs = {"pk": str(pk)} if pk else {}
    view.format_kwarg = None
    view.action = action
    view.headers = {}
    view.check_permissions(op_request)
    return view, op_request


def _create(viewset_class, request, object_id, data):
    view, _ = _build_view(viewset_class, request, "create", data)
    model = view.get_queryset().model
    if model._default_manager.filter(pk=object_id).exists():
        # Ya existía (p. ej. se creó en línea pero el dispositivo no recibió la respuesta).
        instance = view.get_queryset().filter(pk=object_id).first()
        if instance is None:
            raise ValidationError({"id": "El identificador ya está en uso."})
        return http.HTTP_200_OK, view.get_serializer(instance).data
    serializer = view.get_serializer(data=data)
    serializer.is_valid(raise_exception=True)
    # El id es de solo lectura en los serializers; se inyecta el UUID generado en el dispositivo.
    serializer.validated_data["id"] = object_id
    view.perform_create(serializer)
    return http.HTTP_201_CREATED, serializer.data


def _run_view_method(viewset_class, request, action, object_id, data):
    method_name = {"update": "partial_update", "delete": "destroy"}.get(action, action)
    view, op_request = _build_view(viewset_class, request, method_name, data, pk=object_id)
    response = getattr(view, method_name)(op_request, pk=str(object_id))
    return response.status_code, response.data if response.data is not None else {}


def apply_operation(request, op):
    """Aplica una operación y devuelve el resultado que se envía al dispositivo."""
    raw_op_id = op.get("op_id")
    entity = op.get("entity")
    action = op.get("action")
    data = op.get("data") or {}

    try:
        op_id = uuid.UUID(str(raw_op_id))
        object_id = uuid.UUID(str(op.get("object_id")))
    except (TypeError, ValueError):
        return {"op_id": raw_op_id, "status": "rejected", "http_status": 400,
                "errors": {"detail": "op_id u object_id no son UUID válidos."}}

    previous = SyncOperation.objects.filter(user=request.user, op_id=op_id).first()
    if previous:
        return {
            "op_id": str(op_id),
            "status": "duplicate",
            "original_status": previous.status,
            "http_status": previous.http_status,
            "data": previous.response if previous.status == "applied" else None,
            "errors": previous.response if previous.status == "rejected" else None,
        }

    config = WRITABLE_ENTITIES.get(entity)
    if config is None or action not in config[1]:
        return {"op_id": str(op_id), "status": "rejected", "http_status": 400,
                "errors": {"detail": f"Operación no soportada sin conexión: {entity}.{action}"}}
    viewset_class = config[0]

    try:
        with transaction.atomic():
            if action == "create":
                status_code, payload = _create(viewset_class, request, object_id, data)
            else:
                status_code, payload = _run_view_method(
                    viewset_class, request, action, object_id, data
                )
            if status_code >= 400:
                # Las vistas responden 400 sin lanzar excepción en algunas reglas
                # (jornada cerrada, pesaje liquidado...). Revertir por seguridad.
                transaction.set_rollback(True)
    except Http404:
        status_code, payload = 404, {"detail": "El registro no existe o no te pertenece."}
    except APIException as exc:
        status_code, payload = exc.status_code, exc.detail
    except IntegrityError:
        status_code, payload = 409, {"detail": "El registro entra en conflicto con datos existentes."}

    result_status = "applied" if status_code < 400 else "rejected"
    payload = _to_json(payload)
    SyncOperation.objects.create(
        op_id=op_id,
        user=request.user,
        entity=entity,
        action=action,
        object_id=object_id,
        status=result_status,
        http_status=status_code,
        response=payload,
        client_created_at=parse_datetime(op.get("client_ts") or "") if op.get("client_ts") else None,
    )
    return {
        "op_id": str(op_id),
        "status": result_status,
        "http_status": status_code,
        "data": payload if result_status == "applied" else None,
        "errors": payload if result_status == "rejected" else None,
    }


def _to_json(value):
    """Convierte ReturnDict/ErrorDetail/Decimal/UUID a tipos JSON puros."""
    from rest_framework.utils.encoders import JSONEncoder
    import json

    return json.loads(json.dumps(value, cls=JSONEncoder))


def build_snapshot(request):
    """Devuelve todos los datos operativos del usuario con la misma forma que los endpoints de lista."""
    snapshot = {}
    for key, viewset_class in SNAPSHOT_RESOURCES.items():
        view, _ = _build_view(viewset_class, request, "list")
        queryset = view.filter_queryset(view.get_queryset())
        snapshot[key] = view.get_serializer(queryset, many=True).data
    return snapshot
