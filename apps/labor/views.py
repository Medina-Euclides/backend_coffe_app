from django.db import transaction
from django.db.models import ProtectedError
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import IsOwnerOrAdmin
from apps.farms.models import Farm
from .models import Worker, ActivityType, Workday, WorkdayWorker, WorkdayDetail, HarvestRecord
from .serializers import (
    WorkerSerializer,
    ActivityTypeSerializer,
    WorkdaySerializer,
    WorkdayWorkerSerializer,
    WorkdayDetailSerializer,
    HarvestRecordSerializer,
)


class BaseLaborViewSet(viewsets.ModelViewSet):
    """
    Vista base para los recursos del módulo de labor (trabajadores, actividades, jornadas, recolección).
    - Exige autenticación vía JWT (IsAuthenticated).
    - Aplica validación de propiedad por objeto o administrador (IsOwnerOrAdmin).
    - Captura excepciones de clave protegida (ProtectedError) para responder con 400 en vez de 500.
    """

    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]

    def destroy(self, request, *args, **kwargs):
        """
        Manejo seguro de eliminación para evitar errores 500 no controlados
        cuando un registro posee dependencias protegidas en la base de datos.
        """
        instance = self.get_object()
        try:
            instance.delete()
        except ProtectedError:
            return Response(
                {
                    "detail": "No se puede eliminar el registro porque tiene otros datos asociados en el sistema. "
                              "Remueva las dependencias o desactive el registro en su lugar."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class WorkerViewSet(BaseLaborViewSet):
    """
    Gestión de trabajadores del productor.
    Reglas de visibilidad:
      - Administrador: todos los trabajadores del sistema.
      - Productor: solo sus propios trabajadores.
    Reglas de negocio:
      - Sección 2, Regla 1: Cada productor registra a sus trabajadores.
      - Sección 2, Regla 4: Los trabajadores inactivos deben conservar su historial.
    """

    serializer_class = WorkerSerializer
    queryset = Worker.objects.select_related('producer').all()

    def get_queryset(self):
        """
        Filtra los trabajadores pertenecientes al usuario en sesión salvo que sea administrador.
        """
        user = self.request.user
        queryset = super().get_queryset()
        if getattr(user, 'is_administrator', False):
            return queryset
        return queryset.filter(producer=user)

    def perform_create(self, serializer):
        """
        Asigna automáticamente el productor actual como dueño del trabajador
        si no fue especificado o si el usuario no es administrador.
        """
        user = self.request.user
        producer = serializer.validated_data.get('producer') or user
        if not getattr(user, 'is_administrator', False) and producer != user:
            producer = user
        serializer.save(producer=producer)

    def destroy(self, request, *args, **kwargs):
        """
        Eliminación controlada del trabajador.
        Regla de negocio:
          - Si el trabajador ya tiene jornadas asociadas (FK protegida),
            se impide la eliminación física y se sugiere desactivarlo ('is_active': false).
        """
        instance = self.get_object()
        try:
            instance.delete()
        except ProtectedError:
            return Response(
                {
                    "detail": "No se puede eliminar el trabajador porque tiene jornadas laborales asociadas. "
                              "Desactiva el trabajador estableciendo 'is_active': false para conservar su historial."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class ActivityTypeViewSet(BaseLaborViewSet):
    """
    Gestión de tipos de actividad laboral (labores culturales, recolección, etc.).
    Reglas de negocio:
      - Sección 3, Reglas 1 y 2: El productor define libremente sus actividades sin catálogo fijo.
      - Sección 3, Regla 5: Las actividades de recolección se diferencian con 'is_harvest'.
    """

    serializer_class = ActivityTypeSerializer
    queryset = ActivityType.objects.select_related('producer').all()

    def get_queryset(self):
        """
        Filtra los tipos de actividad para que cada productor solo consulte los suyos.
        """
        user = self.request.user
        queryset = super().get_queryset()
        if getattr(user, 'is_administrator', False):
            return queryset
        return queryset.filter(producer=user)

    def perform_create(self, serializer):
        """
        Asigna el usuario autenticado como productor propietario del tipo de labor.
        """
        user = self.request.user
        producer = serializer.validated_data.get('producer') or user
        if not getattr(user, 'is_administrator', False) and producer != user:
            producer = user
        serializer.save(producer=producer)

    def destroy(self, request, *args, **kwargs):
        """
        Eliminación controlada de tipos de actividad con dependencias protegidas.
        """
        instance = self.get_object()
        try:
            instance.delete()
        except ProtectedError:
            return Response(
                {
                    "detail": "No se puede eliminar el tipo de actividad porque se encuentra registrado en jornadas laborales existentes."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class WorkdayViewSet(BaseLaborViewSet):
    """
    Registro y consulta de jornadas diarias de una finca.
    Reglas de negocio:
      - Sección 4, Regla 1: La jornada identifica al productor, la finca y la fecha.
      - Sección 4, Regla 4: Solo existe una jornada por productor, finca y fecha.
    """

    serializer_class = WorkdaySerializer
    queryset = Workday.objects.select_related("producer", "farm").prefetch_related(
        "participants__worker",
        "participants__details__activity_type",
        "participants__details__lot",
        "participants__details__harvest_records",
    )

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        if getattr(user, 'is_administrator', False):
            return queryset
        return queryset.filter(producer=user)

    def perform_create(self, serializer):
        farm = serializer.validated_data["farm"]
        serializer.save(producer=farm.id_productor)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.is_closed:
            return Response(
                {"detail": "No se puede eliminar una jornada cerrada. Se conserva su historial."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if instance.participants.exists():
            return Response(
                {"detail": "No se puede eliminar la jornada porque tiene participaciones asociadas."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="close")
    def close(self, request, pk=None):
        """Cierra la jornada para impedir modificaciones posteriores."""
        workday = self.get_object()
        if workday.is_closed:
            return Response(
                {"detail": "La jornada ya está cerrada."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        workday.status = Workday.Status.CLOSED
        workday.closed_at = timezone.now()
        workday.save(update_fields=["status", "closed_at"])
        return Response(self.get_serializer(workday).data, status=status.HTTP_200_OK)


class WorkdayWorkerViewSet(BaseLaborViewSet):
    """Gestiona la participación y el acuerdo diario de cada trabajador."""

    serializer_class = WorkdayWorkerSerializer
    queryset = WorkdayWorker.objects.select_related(
        "worker",
        "workday",
        "workday__producer",
        "workday__farm",
    ).prefetch_related("details", "details__harvest_records")

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        if getattr(user, "is_administrator", False):
            return queryset
        return queryset.filter(workday__producer=user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.is_locked:
            return Response(
                {"detail": "No se puede eliminar una participación liquidada, anulada o incluida en una liquidación."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if instance.workday.is_closed:
            return Response(
                {"detail": "No se puede eliminar una participación de una jornada cerrada."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """Anula una participación pendiente y sus pesajes aún no liquidados."""
        participation = self.get_object()
        if participation.is_locked:
            return Response(
                {"detail": "No se puede anular una participación liquidada o incluida en una liquidación."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            participation.settlement_status = WorkdayWorker.SettlementStatus.CANCELED
            participation.save(update_fields=["settlement_status"])
            HarvestRecord.objects.filter(
                workday_detail__workday_worker=participation,
                settlement_status=HarvestRecord.SettlementStatus.REGISTERED,
            ).update(settlement_status=HarvestRecord.SettlementStatus.CANCELED)
        return Response(self.get_serializer(participation).data, status=status.HTTP_200_OK)


class WorkdayDetailViewSet(BaseLaborViewSet):
    """
    Detalle de la labor ejecutada: vincula una jornada con un lote específico y tipo de labor.
    Reglas de negocio:
      - Sección 4, Regla 2: El lote es obligatorio para registrar la ejecución.
      - Sección 1, Regla 5: La información de fincas diferentes no debe mezclarse.
    """

    serializer_class = WorkdayDetailSerializer
    queryset = WorkdayDetail.objects.select_related(
        "activity_type",
        "workday_worker__worker",
        "workday_worker__workday__producer",
        "workday_worker__workday__farm",
        "lot",
    ).prefetch_related("harvest_records")

    def get_queryset(self):
        """
        Filtra los detalles de jornada que pertenezcan al productor autenticado.
        """
        user = self.request.user
        queryset = super().get_queryset()
        if getattr(user, 'is_administrator', False):
            return queryset
        return queryset.filter(workday_worker__workday__producer=user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.workday_worker.is_locked:
            return Response(
                {"detail": "No se puede eliminar un detalle de una participación liquidada o anulada."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if instance.workday_worker.workday.is_closed:
            return Response(
                {"detail": "No se puede eliminar un detalle de una jornada cerrada."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if instance.harvest_records.filter(settlement_status="liquidado").exists():
            return Response(
                {"detail": "No se puede eliminar un detalle con pesajes liquidados."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)


class HarvestRecordViewSet(BaseLaborViewSet):
    """
    Registros de pesaje de recolección de café expresados en kilogramos.
    Reglas de negocio:
      - Sección 5, Regla 1: Cada registro de recolección debe asociarse al detalle de una jornada.
      - Sección 5, Regla 2: La cantidad debe expresarse en kilogramos.
    """

    serializer_class = HarvestRecordSerializer
    queryset = HarvestRecord.objects.select_related(
        "workday_detail__activity_type",
        "workday_detail__workday_worker__workday__producer",
    )

    def get_queryset(self):
        """
        Filtra las recolecciones asociadas a jornadas del productor autenticado.
        """
        user = self.request.user
        queryset = super().get_queryset()
        if getattr(user, 'is_administrator', False):
            return queryset
        return queryset.filter(
            workday_detail__workday_worker__workday__producer=user
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.is_locked:
            return Response(
                {"detail": "No se puede eliminar un pesaje liquidado o incluido en una liquidación."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if instance.workday_detail.workday_worker.workday.is_closed:
            return Response(
                {"detail": "No se puede eliminar un pesaje de una jornada cerrada."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """Anula un pesaje registrado que todavía no haya sido liquidado."""
        harvest = self.get_object()
        if harvest.is_locked:
            return Response(
                {"detail": "No se puede anular un pesaje liquidado o incluido en una liquidación."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        harvest.settlement_status = HarvestRecord.SettlementStatus.CANCELED
        harvest.save(update_fields=["settlement_status"])
        return Response(self.get_serializer(harvest).data, status=status.HTTP_200_OK)
