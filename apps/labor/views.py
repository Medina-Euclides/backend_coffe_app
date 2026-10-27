from django.db.models import ProtectedError
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import IsOwnerOrAdmin
from apps.farms.models import Farm
from .models import Worker, ActivityType, Workday, WorkdayDetail, HarvestRecord
from .serializers import (
    WorkerSerializer,
    ActivityTypeSerializer,
    WorkdaySerializer,
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
    Registro y consulta de jornadas laborales diarias de los trabajadores.
    Reglas de negocio:
      - Sección 4, Regla 1: Cada jornada identifica al trabajador y la fecha de ejecución.
      - Sección 4, Regla 4: Cada ejecución de un trabajador en una fecha es independiente y única.
    """

    serializer_class = WorkdaySerializer
    queryset = Workday.objects.select_related('worker', 'worker__producer').prefetch_related('details', 'details__harvest_records').all()

    def get_queryset(self):
        """
        Filtra las jornadas cuyos trabajadores pertenezcan al productor autenticado.
        """
        user = self.request.user
        queryset = super().get_queryset()
        if getattr(user, 'is_administrator', False):
            return queryset
        return queryset.filter(worker__producer=user)


class WorkdayDetailViewSet(BaseLaborViewSet):
    """
    Detalle de la labor ejecutada: vincula una jornada con un lote específico y tipo de labor.
    Reglas de negocio:
      - Sección 4, Regla 2: El lote es obligatorio para registrar la ejecución.
      - Sección 1, Regla 5: La información de fincas diferentes no debe mezclarse.
    """

    serializer_class = WorkdayDetailSerializer
    queryset = WorkdayDetail.objects.select_related('activity_type', 'workday', 'lot', 'workday__worker__producer').prefetch_related('harvest_records').all()

    def get_queryset(self):
        """
        Filtra los detalles de jornada que pertenezcan al productor autenticado.
        """
        user = self.request.user
        queryset = super().get_queryset()
        if getattr(user, 'is_administrator', False):
            return queryset
        return queryset.filter(workday__worker__producer=user)


class HarvestRecordViewSet(BaseLaborViewSet):
    """
    Registros de pesaje de recolección de café expresados en kilogramos.
    Reglas de negocio:
      - Sección 5, Regla 1: Cada registro de recolección debe asociarse al detalle de una jornada.
      - Sección 5, Regla 2: La cantidad debe expresarse en kilogramos.
    """

    serializer_class = HarvestRecordSerializer
    queryset = HarvestRecord.objects.select_related('workday_detail', 'workday_detail__workday__worker__producer').all()

    def get_queryset(self):
        """
        Filtra las recolecciones asociadas a jornadas del productor autenticado.
        """
        user = self.request.user
        queryset = super().get_queryset()
        if getattr(user, 'is_administrator', False):
            return queryset
        return queryset.filter(workday_detail__workday__worker__producer=user)
