# ---------------------------------------------------------------------------
# SERVICIOS DE NEGOCIO - MÓDULO PRODUCTION
# ---------------------------------------------------------------------------
# Aquí va toda la lógica: consolidación de producción desde registros de
# recolección (labor), cálculos, filtros por periodo. Los serializers solo
# validan datos; las vistas solo reciben peticiones, invocan servicios y
# devuelven respuesta HTTP.

from decimal import Decimal

from django.db.models import Sum, Count

from apps.labor.models import HarvestRecord
from .models import Sale


class ProductionService:
    """Servicio para consolidar producción de café recolectado e ingresos por ventas."""

    @staticmethod
    def get_production_by_farm(*, user, farm_id=None, year=None, month=None):
        """
        Consolida la producción total de café recolectado por finca.
        Toma datos desde HarvestRecord en labor, filtrando por productor/finca/periodo.
        """
        # Base queryset: registros de recolección del productor
        qs = (
            HarvestRecord.objects.select_related(
                "workday_detail__workday__worker",
                "workday_detail__lot__id_farm",
            )
            .filter(workday_detail__workday__worker__producer=user)
        )

        # Filtrar por finca si se especifica
        if farm_id is not None:
            qs = qs.filter(workday_detail__lot__id_farm_id=farm_id)

        # Filtrar por año/mes desde la fecha de la jornada
        if year is not None:
            qs = qs.filter(workday_detail__workday__date__year=year)
        if month is not None:
            qs = qs.filter(workday_detail__workday__date__month=month)

        # Agrupar por finca
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

        data = []
        for item in results:
            data.append(
                {
                    "farm_id": item["workday_detail__lot__id_farm_id"],
                    "farm_name": item["workday_detail__lot__id_farm__name"],
                    "total_quantity_kg": item["total_quantity_kg"] or Decimal("0"),
                    "total_harvest_records": item["total_harvest_records"],
                }
            )
        return data

    @staticmethod
    def get_production_by_lot(*, user, farm_id=None, lot_id=None, year=None, month=None):
        """
        Consolida la producción total de café recolectado por lote.
        Toma datos desde HarvestRecord en labor, filtrando por productor/finca/lote/periodo.
        """
        # Base queryset: registros de recolección del productor
        qs = (
            HarvestRecord.objects.select_related(
                "workday_detail__workday__worker",
                "workday_detail__lot__id_farm",
            )
            .filter(workday_detail__workday__worker__producer=user)
        )

        # Filtrar por finca si se especifica
        if farm_id is not None:
            qs = qs.filter(workday_detail__lot__id_farm_id=farm_id)
        # Filtrar por lote si se especifica
        if lot_id is not None:
            qs = qs.filter(workday_detail__lot_id=lot_id)

        # Filtrar por año/mes desde la fecha de la jornada
        if year is not None:
            qs = qs.filter(workday_detail__workday__date__year=year)
        if month is not None:
            qs = qs.filter(workday_detail__workday__date__month=month)

        # Agrupar por lote
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

        data = []
        for item in results:
            data.append(
                {
                    "lot_id": item["workday_detail__lot_id"],
                    "lot_name": item["workday_detail__lot__name"],
                    "farm_id": item["workday_detail__lot__id_farm_id"],
                    "farm_name": item["workday_detail__lot__id_farm__name"],
                    "total_quantity_kg": item["total_quantity_kg"] or Decimal("0"),
                    "total_harvest_records": item["total_harvest_records"],
                }
            )
        return data

    @staticmethod
    def get_revenue_by_farm(*, user, farm_id=None, year=None, month=None):
        """Consolida los ingresos por finca desde ventas activas, con filtros de periodo."""
        # Base: solo ventas activas (el histórico desactivado no suma ingresos).
        qs = Sale.objects.select_related("farm").filter(is_active=True)

        # Los productores solo ven sus fincas; el admin (user=None) ve todas.
        if user is not None:
            qs = qs.filter(farm__id_productor=user)

        # Filtros opcionales por finca y periodo de venta.
        if farm_id is not None:
            qs = qs.filter(farm_id=farm_id)
        if year is not None:
            qs = qs.filter(sale_date__year=year)
        if month is not None:
            qs = qs.filter(sale_date__month=month)

        # Agrupar por finca sumando ingresos, ventas y kilogramos.
        results = (
            qs.values("farm_id", "farm__name")
            .annotate(
                total_revenue=Sum("total_amount"),
                total_sales=Count("id"),
                total_quantity_kg=Sum("quantity_kg"),
            )
            .order_by("farm__name")
        )

        data = []
        for item in results:
            data.append(
                {
                    "farm_id": item["farm_id"],
                    "farm_name": item["farm__name"],
                    "total_revenue": item["total_revenue"] or Decimal("0"),
                    "total_sales": item["total_sales"],
                    "total_quantity_kg": item["total_quantity_kg"] or Decimal("0"),
                }
            )
        return data
