from django.db.models import ProtectedError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import IsOwnerOrAdmin
from .models import Sale
from .serializers import (
    FarmProductionSummarySerializer,
    LotProductionSummarySerializer,
    ProductionFilterSerializer,
    SaleSerializer,
)
from .services import ProductionService


# ---------------------------------------------------------------------------
# VIEWSETS - SOLO RECIBEN, INVOCAN SERVICIO Y RESPONDEN
# ---------------------------------------------------------------------------


class BaseProductionViewSet(viewsets.ModelViewSet):
    """Base con auth y permisos."""
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]


class SaleViewSet(BaseProductionViewSet):
    """CRUD de ventas de café."""
    serializer_class = SaleSerializer
    queryset = Sale.objects.select_related("farm").all()

    def get_queryset(self):
        """Filtra ventas por finca del productor o todas si es administrador."""
        user = self.request.user
        queryset = super().get_queryset()
        if getattr(user, "is_administrator", False):
            return queryset
        return queryset.filter(farm__id_productor=user)

    def perform_create(self, serializer):
        """Valida pertenencia de finca al productor."""
        user = self.request.user
        farm = serializer.validated_data.get("farm")
        if farm and not getattr(user, "is_administrator", False) and farm.id_productor != user:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("No puedes registrar ventas para fincas ajenas.")
        serializer.save()


class ProductionViewSet(BaseProductionViewSet):
    """Consolidación de producción desde registros de recolección en labor."""
    serializer_class = None
    queryset = Sale.objects.none()

    @action(detail=False, methods=["get"], url_path="by-farm")
    def by_farm(self, request):
        """Consolida producción total por finca filtrada por año/mes."""
        filter_serializer = ProductionFilterSerializer(data=request.query_params)
        filter_serializer.is_valid(raise_exception=True)
        data = filter_serializer.validated_data

        user = request.user
        # Si es productor, filtrar solo sus fincas; si es admin, puede filtrar por cualquier finca
        farm_id = data.get("farm_id")
        if farm_id and not getattr(user, "is_administrator", False):
            from apps.farms.models import Farm

            try:
                farm = Farm.objects.get(id=farm_id)
                if farm.id_productor != user:
                    from rest_framework.exceptions import PermissionDenied

                    raise PermissionDenied("No tienes permisos sobre esta finca.")
            except Farm.DoesNotExist:
                return Response({"detail": "Finca no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        result = ProductionService.get_production_by_farm(
            user=user if not getattr(user, "is_administrator", False) else None,
            farm_id=farm_id,
            year=data.get("year"),
            month=data.get("month"),
        )
        # Ajustar para admin - si es admin y no filtra por productor específico, obtener todos
        if getattr(user, "is_administrator", False) and farm_id is None:
            # Para admin sin filtro de finca específica, obtener de todas las fincas
            from apps.labor.models import HarvestRecord
            from django.db.models import Sum, Count
            from decimal import Decimal

            qs = HarvestRecord.objects.select_related(
                "workday_detail__lot__id_farm",
            ).all()
            if data.get("year") is not None:
                qs = qs.filter(workday_detail__workday__date__year=data["year"])
            if data.get("month") is not None:
                qs = qs.filter(workday_detail__workday__date__month=data["month"])
            results = (
                qs.values(
                    "workday_detail__lot__id_farm_id",
                    "workday_detail__lot__id_farm__name",
                )
                .annotate(
                    total_quantity_kg=Sum("quantity_kg"),
                    total_harvest_records=Count("id"),
                )
                .order_by("workday_detail__lot__id_farm__name")
            )
            result = []
            for item in results:
                result.append(
                    {
                        "farm_id": item["workday_detail__lot__id_farm_id"],
                        "farm_name": item["workday_detail__lot__id_farm__name"],
                        "total_quantity_kg": item["total_quantity_kg"] or Decimal("0"),
                        "total_harvest_records": item["total_harvest_records"],
                    }
                )
        serializer = FarmProductionSummarySerializer(result, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="by-lot")
    def by_lot(self, request):
        """Consolida producción total por lote filtrada por finca/año/mes."""
        filter_serializer = ProductionFilterSerializer(data=request.query_params)
        filter_serializer.is_valid(raise_exception=True)
        data = filter_serializer.validated_data

        user = request.user
        farm_id = data.get("farm_id")
        lot_id = data.get("lot_id")

        if not getattr(user, "is_administrator", False):
            from apps.farms.models import Farm, Lot

            if farm_id:
                try:
                    farm = Farm.objects.get(id=farm_id)
                    if farm.id_productor != user:
                        from rest_framework.exceptions import PermissionDenied
                        raise PermissionDenied("No tienes permisos sobre esta finca.")
                except Farm.DoesNotExist:
                    return Response({"detail": "Finca no encontrada."}, status=status.HTTP_404_NOT_FOUND)
            if lot_id:
                try:
                    lot = Lot.objects.select_related("id_farm").get(id=lot_id)
                    if lot.id_farm.id_productor != user:
                        from rest_framework.exceptions import PermissionDenied
                        raise PermissionDenied("No tienes permisos sobre este lote.")
                except Lot.DoesNotExist:
                    return Response({"detail": "Lote no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        if getattr(user, "is_administrator", False) and farm_id is None and lot_id is None:
            from apps.labor.models import HarvestRecord
            from django.db.models import Sum, Count
            from decimal import Decimal

            qs = HarvestRecord.objects.select_related(
                "workday_detail__lot__id_farm",
            ).all()
            if data.get("year") is not None:
                qs = qs.filter(workday_detail__workday__date__year=data["year"])
            if data.get("month") is not None:
                qs = qs.filter(workday_detail__workday__date__month=data["month"])
            results = (
                qs.values(
                    "workday_detail__lot_id",
                    "workday_detail__lot__name",
                    "workday_detail__lot__id_farm_id",
                    "workday_detail__lot__id_farm__name",
                )
                .annotate(
                    total_quantity_kg=Sum("quantity_kg"),
                    total_harvest_records=Count("id"),
                )
                .order_by("workday_detail__lot__id_farm__name", "workday_detail__lot__name")
            )
            result = []
            for item in results:
                result.append(
                    {
                        "lot_id": item["workday_detail__lot_id"],
                        "lot_name": item["workday_detail__lot__name"],
                        "farm_id": item["workday_detail__lot__id_farm_id"],
                        "farm_name": item["workday_detail__lot__id_farm__name"],
                        "total_quantity_kg": item["total_quantity_kg"] or Decimal("0"),
                        "total_harvest_records": item["total_harvest_records"],
                    }
                )
        else:
            result = ProductionService.get_production_by_lot(
                user=user,
                farm_id=farm_id,
                lot_id=lot_id,
                year=data.get("year"),
                month=data.get("month"),
            )

        serializer = LotProductionSummarySerializer(result, many=True)
        return Response(serializer.data)
