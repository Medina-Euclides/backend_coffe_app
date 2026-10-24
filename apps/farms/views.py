from django.db.models import ProtectedError
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import IsOwnerOrAdmin
from .models import Farm, Lot
from .serializers import FarmSerializer, LotSerializer


class BaseFarmViewSet(viewsets.ModelViewSet):
    """
    Base de las vistas de fincas y lotes.

    - Exige token (IsAuthenticated) siempre.
    - Aplica el permiso por objeto (dueño / administrador).
    - Los listados se filtran en get_queryset() para que cada usuario
      vea únicamente lo que le corresponde.
    """

    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]


class FarmView(BaseFarmViewSet):
    """
    Fincas del productor.
    Reglas de visibilidad:
      - Administrador: todas las fincas.
      - Productor: solo las fincas de las que es dueño.
    """

    serializer_class = FarmSerializer
    queryset = Farm.objects.select_related('id_productor').prefetch_related('lots').all()

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        if user.is_administrator:
            return queryset
        return queryset.filter(id_productor=user)

    def perform_create(self, serializer):
        user = self.request.user
        producer = serializer.validated_data.get('id_productor') or user
        serializer.save(id_productor=producer)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            instance.delete()
        except ProtectedError:
            return Response(
                {"detail": "No se puede eliminar la finca porque tiene lotes asociados. Elimina o transfiere los lotes primero."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class LotView(BaseFarmViewSet):
    """
    Lotes de las fincas.
    Reglas de visibilidad:
      - Administrador: todos los lotes.
      - Productor: los lotes de sus fincas.
    """

    serializer_class = LotSerializer
    queryset = Lot.objects.select_related('id_farm', 'id_farm__id_productor').all()

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        if user.is_administrator:
            return queryset
        return queryset.filter(id_farm__id_productor=user)
