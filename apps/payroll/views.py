from django.db import transaction
from django.db.models import ProtectedError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import IsOwnerOrAdmin
from .models import LaborPayment, Settlement, SettlementDetailHarvest, SettlementDetailWorkday
from .serializers import (
    AddHarvestDetailSerializer,
    AddWorkdayDetailSerializer,
    CloseSettlementSerializer,
    LaborPaymentSerializer,
    PaySettlementSerializer,
    SettleAndPaySerializer,
    SettlementDetailHarvestSerializer,
    SettlementDetailWorkdaySerializer,
    SettlementSerializer,
)
from .services import PayrollService


# ---------------------------------------------------------------------------
# VIEWSETS - SOLO RECIBEN, INVOCAN SERVICIO Y RESPONDEN
# ---------------------------------------------------------------------------


class BasePayrollViewSet(viewsets.ModelViewSet):
    """Base con auth y permisos."""
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]


class SettlementViewSet(BasePayrollViewSet):
    """CRUD de liquidaciones + acciones delegadas a servicios."""
    serializer_class = SettlementSerializer
    queryset = (
        Settlement.objects.select_related("worker", "farm", "worker__producer")
        .prefetch_related("workday_details", "harvest_details", "payment")
        .all()
    )

    def get_queryset(self):
        # Filtra por productor o todo si es admin
        user = self.request.user
        queryset = super().get_queryset()
        # Filtro opcional ?status=pagada (historial de pagos, solo en línea).
        status_filter = self.request.query_params.get("status")
        if self.action == "list" and status_filter in Settlement.Status.values:
            queryset = queryset.filter(status=status_filter)
        if getattr(user, "is_administrator", False):
            return queryset
        return queryset.filter(worker__producer=user)

    def _ensure_settlement_access(self, settlement_id):
        """
        Regla de negocio (SRS módulo 1, regla 7): un productor solo puede
        operar sobre sus propias liquidaciones. Se responde 404 para no
        revelar la existencia de liquidaciones ajenas.
        """
        if not self.get_queryset().filter(id=settlement_id).exists():
            raise NotFound("Liquidación no encontrada.")

    def perform_create(self, serializer):
        # Fuerza pertenencia al productor
        user = self.request.user
        worker = serializer.validated_data.get("worker")
        if worker and not getattr(user, "is_administrator", False) and worker.producer != user:
            raise PermissionDenied("No puedes crear liquidaciones para trabajadores ajenos.")

        # La regla «una sola liquidación abierta por trabajador» (SRS módulo 7,
        # regla 4) se valida en SettlementSerializer.validate().

        # Aislamiento multi-tenant: la finca debe pertenecer al productor.
        farm = serializer.validated_data.get("farm")
        if farm and not getattr(user, "is_administrator", False) and farm.id_productor_id != user.id:
            raise PermissionDenied("No puedes crear liquidaciones para fincas ajenas.")

        # Coherencia de datos: el trabajador y la finca deben pertenecer al mismo productor.
        if worker and farm and farm.id_productor_id != worker.producer_id:
            raise ValidationError(
                {"farm": "La finca debe pertenecer al mismo productor que el trabajador."}
            )

        serializer.save()

    def update(self, request, *args, **kwargs):
        """Una liquidación cerrada o pagada no puede modificarse (SRS módulo 7, regla 8)."""
        instance = self.get_object()
        if instance.status != Settlement.Status.OPEN:
            return Response(
                {"detail": "No se puede modificar una liquidación cerrada o pagada."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        """Una liquidación cerrada o pagada no puede modificarse (SRS módulo 7, regla 8)."""
        instance = self.get_object()
        if instance.status != Settlement.Status.OPEN:
            return Response(
                {"detail": "No se puede modificar una liquidación cerrada o pagada."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """
        Solo se eliminan liquidaciones abiertas. Las cerradas y pagadas
        conservan su historial (SRS módulo 7, regla 7).
        """
        instance = self.get_object()
        if instance.status != Settlement.Status.OPEN:
            return Response(
                {
                    "detail": "No se puede eliminar una liquidación cerrada o pagada. "
                              "Se conserva su historial."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            instance.delete()
        except ProtectedError:
            return Response(
                {"detail": "No se puede eliminar la liquidación porque tiene detalles asociados."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["post"], url_path="add-workday")
    def add_workday(self, request):
        """Añade jornada por jornal via servicio."""
        serializer = AddWorkdayDetailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        self._ensure_settlement_access(data["settlement_id"])
        try:
            detail = PayrollService.add_workday_to_settlement(
                settlement_id=data["settlement_id"],
                workday_worker_id=data["workday_worker_id"],
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            SettlementDetailWorkdaySerializer(detail).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"], url_path="add-harvest")
    def add_harvest(self, request):
        """Añade pesaje por kg via servicio."""
        serializer = AddHarvestDetailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        self._ensure_settlement_access(data["settlement_id"])
        try:
            detail = PayrollService.add_harvest_to_settlement(
                settlement_id=data["settlement_id"],
                harvest_record_id=data["harvest_record_id"],
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            SettlementDetailHarvestSerializer(detail).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"], url_path="close")
    def close(self, request):
        """Cierra liquidación via servicio."""
        serializer = CloseSettlementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        self._ensure_settlement_access(data["settlement_id"])
        try:
            settlement = PayrollService.close_settlement(
                settlement_id=data["settlement_id"]
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(SettlementSerializer(settlement).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="pay")
    def pay(self, request):
        """Registra pago via servicio."""
        serializer = PaySettlementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        self._ensure_settlement_access(data["settlement_id"])
        try:
            payment = PayrollService.pay_settlement(
                settlement_id=data["settlement_id"],
                date=data["date"],
                amount_paid=data["amount_paid"],
                payment_method=data["payment_method"],
                notes=data.get("notes", ""),
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(LaborPaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


    @action(detail=False, methods=["post"], url_path="settle-and-pay")
    def settle_and_pay(self, request, pk=None):
        """
        Liquida y paga en una sola operación atómica. Es la acción que usa la app
        tanto en línea como al sincronizar la cola offline (entity=settlement).
        """
        serializer = SettleAndPaySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        settlement_id = data["settlement_id"]

        with transaction.atomic():
            if Settlement.objects.filter(pk=settlement_id).exists():
                self._ensure_settlement_access(settlement_id)
            else:
                missing = [f for f in ("worker", "farm", "start_date", "end_date") if not data.get(f)]
                if missing:
                    raise ValidationError({f: "Este campo es requerido." for f in missing})
                create_serializer = self.get_serializer(
                    data={
                        "worker": str(data["worker"]),
                        "farm": str(data["farm"]),
                        "start_date": data["start_date"],
                        "end_date": data["end_date"],
                    }
                )
                create_serializer.is_valid(raise_exception=True)
                # El id lo genera el dispositivo: así un reenvío no crea otra liquidación.
                create_serializer.validated_data["id"] = settlement_id
                self.perform_create(create_serializer)
            try:
                settlement = PayrollService.settle_and_pay(
                    settlement_id=settlement_id,
                    workday_worker_ids=data["workday_worker_ids"],
                    harvest_record_ids=data["harvest_record_ids"],
                    date=data["date"],
                    amount_paid=data["amount_paid"],
                    payment_method=data["payment_method"],
                    notes=data.get("notes", ""),
                )
            except ValueError as e:
                transaction.set_rollback(True)
                return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        settlement = Settlement.objects.get(pk=settlement.pk)
        return Response(SettlementSerializer(settlement).data, status=status.HTTP_200_OK)


class SettlementDetailWorkdayViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Consulta (solo lectura) de los detalles por jornal.
    Las mutaciones solo se realizan mediante las acciones del servicio de
    liquidaciones, para preservar la integridad de tarifas e importes.
    """
    serializer_class = SettlementDetailWorkdaySerializer
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]
    queryset = SettlementDetailWorkday.objects.select_related(
        "settlement", "workday_worker", "settlement__worker__producer"
    ).all()

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        if getattr(user, "is_administrator", False):
            return queryset
        return queryset.filter(settlement__worker__producer=user)


class SettlementDetailHarvestViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Consulta (solo lectura) de los detalles por kilogramo.
    Las mutaciones solo se realizan mediante las acciones del servicio.
    """
    serializer_class = SettlementDetailHarvestSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]
    queryset = SettlementDetailHarvest.objects.select_related(
        "settlement", "harvest_record", "settlement__worker__producer"
    ).all()

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        if getattr(user, "is_administrator", False):
            return queryset
        return queryset.filter(settlement__worker__producer=user)


class LaborPaymentViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Consulta (solo lectura) de los pagos laborales.
    Los pagos solo se registran mediante la acción `pay`, evitando duplicados
    y montos inconsistentes (SRS módulo 8, regla 6).
    """
    serializer_class = LaborPaymentSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]
    queryset = LaborPayment.objects.select_related(
        "settlement", "settlement__worker__producer"
    ).all()

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        if getattr(user, "is_administrator", False):
            return queryset
        return queryset.filter(settlement__worker__producer=user)
