from datetime import timedelta
from decimal import Decimal

from django.db.models import F, Q, Sum
from django.utils import timezone

from apps.farms.models import Farm, Lot
from apps.finance.models import OperatingExpense
from apps.labor.models import HarvestRecord
from apps.production.models import Sale


ZERO_MONEY = Decimal("0.00")
ZERO_KILOGRAMS = Decimal("0.000")
# Años que cubre el histórico (period="all"), contando el actual.
HISTORY_YEARS = 5


WORKDAY_DATE = "workday_detail__workday_worker__workday__date"


def period_start(period, today):
    """Primer día del período (semana desde el lunes, mes, año o histórico)."""
    if period == "week":
        return today - timedelta(days=today.weekday())
    if period == "month":
        return today.replace(day=1)
    if period == "year":
        return today.replace(month=1, day=1)
    if period == "all":
        return today.replace(year=today.year - (HISTORY_YEARS - 1), month=1, day=1)
    raise ValueError(f"Unsupported analytics period: {period}")


class AnalyticsService:
    @classmethod
    def get_summary(
        cls,
        *,
        user,
        farm_id=None,
        selected_farm=None,
        period="month",
        today=None,
    ):
        today = today or timezone.localdate()
        farm_scope = Farm.objects.all()
        if not getattr(user, "is_administrator", False):
            farm_scope = farm_scope.filter(id_productor=user)
        if farm_id is not None:
            farm_scope = farm_scope.filter(id=farm_id)

        # Todo el resumen (tarjetas, gastos, lotes y gráfico) usa el mismo rango.
        start_date = period_start(period, today)
        expenses = OperatingExpense.objects.filter(
            farm__in=farm_scope,
            date__range=(start_date, today),
        )
        sales = Sale.objects.filter(
            farm__in=farm_scope,
            is_active=True,
            sale_date__range=(start_date, today),
        )
        harvest_records = HarvestRecord.objects.filter(
            workday_detail__lot__id_farm__in=farm_scope,
            workday_detail__activity_type__is_harvest=True,
        ).exclude(settlement_status=HarvestRecord.SettlementStatus.CANCELED)

        if not getattr(user, "is_administrator", False):
            harvest_records = harvest_records.filter(
                workday_detail__workday_worker__workday__producer=user
            )

        expenses_by_category = cls._expenses_by_category(expenses)
        total_expenses = sum(
            (item["total_amount"] for item in expenses_by_category),
            ZERO_MONEY,
        )
        sales_income = sales.aggregate(total=Sum("total_amount"))["total"] or ZERO_MONEY

        production_by_lot = cls._production_by_lot(
            harvest_records=harvest_records.filter(
                **{f"{WORKDAY_DATE}__range": (start_date, today)}
            ),
            farms=farm_scope,
        )
        production_by_period = cls._production_by_period(
            harvest_records=harvest_records,
            today=today,
        )
        production_series = cls._production_series(
            harvest_records=harvest_records,
            period=period,
            today=today,
        )

        return {
            "farm_id": selected_farm.id if selected_farm else None,
            "farm_name": selected_farm.name if selected_farm else None,
            "period": period,
            "expenses_by_category": expenses_by_category,
            "financial_summary": {
                "sales_income": sales_income,
                "total_expenses": total_expenses,
                "net_income": sales_income - total_expenses,
            },
            "production_by_lot": production_by_lot,
            "production_by_period": production_by_period,
            "production_series": production_series,
        }

    @staticmethod
    def _expenses_by_category(expenses):
        totals = {
            item["category"]: item["total_amount"]
            for item in expenses.values("category").annotate(
                total_amount=Sum("amount")
            )
        }
        return [
            {
                "category": category,
                "label": label,
                "total_amount": totals.get(category, ZERO_MONEY),
            }
            for category, label in OperatingExpense.Category.choices
        ]

    @staticmethod
    def _production_by_lot(*, harvest_records, farms):
        totals_by_lot = {
            item["workday_detail__lot_id"]: item["total_quantity_kg"]
            for item in harvest_records.values(
                "workday_detail__lot_id"
            ).annotate(total_quantity_kg=Sum("quantity_kg"))
        }
        lots = (
            Lot.objects.filter(id_farm__in=farms)
            .select_related("id_farm")
            .order_by("id_farm__name", "name")
        )
        return [
            {
                "lot_id": lot.id,
                "lot_name": lot.name,
                "farm_id": lot.id_farm_id,
                "farm_name": lot.id_farm.name,
                "plant_count": lot.plant_count,
                "total_quantity_kg": totals_by_lot.get(lot.id, ZERO_KILOGRAMS),
            }
            for lot in lots
        ]

    @staticmethod
    def _production_by_period(*, harvest_records, today):
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)
        year_start = today.replace(month=1, day=1)

        totals = harvest_records.aggregate(
            week=Sum(
                "quantity_kg",
                filter=Q(
                    workday_detail__workday_worker__workday__date__range=(
                        week_start,
                        today,
                    )
                ),
            ),
            month=Sum(
                "quantity_kg",
                filter=Q(
                    workday_detail__workday_worker__workday__date__range=(
                        month_start,
                        today,
                    )
                ),
            ),
            year=Sum(
                "quantity_kg",
                filter=Q(
                    workday_detail__workday_worker__workday__date__range=(
                        year_start,
                        today,
                    )
                ),
            ),
        )

        return {
            "week": {
                "start_date": week_start,
                "end_date": today,
                "total_quantity_kg": totals["week"] or ZERO_KILOGRAMS,
            },
            "month": {
                "start_date": month_start,
                "end_date": today,
                "total_quantity_kg": totals["month"] or ZERO_KILOGRAMS,
            },
            "year": {
                "start_date": year_start,
                "end_date": today,
                "total_quantity_kg": totals["year"] or ZERO_KILOGRAMS,
            },
        }

    @staticmethod
    def _production_series(*, harvest_records, period, today):
        start_date = period_start(period, today)
        if period == "week":
            bucket_count = (today - start_date).days + 1
            bucket_index = lambda workday_date: (workday_date - start_date).days
        elif period == "month":
            bucket_count = (today.day + 6) // 7
            bucket_index = lambda workday_date: (workday_date.day - 1) // 7
        elif period == "year":
            bucket_count = today.month
            bucket_index = lambda workday_date: workday_date.month - 1
        else:  # "all": un punto por año
            bucket_count = HISTORY_YEARS
            bucket_index = lambda workday_date: workday_date.year - start_date.year
        date_expression = F(WORKDAY_DATE)

        daily_totals = {
            item["workday_date"]: item["total_quantity_kg"]
            for item in harvest_records.filter(
                workday_detail__workday_worker__workday__date__range=(
                    start_date,
                    today,
                )
            )
            .values(workday_date=date_expression)
            .annotate(total_quantity_kg=Sum("quantity_kg"))
        }
        totals_by_bucket = [ZERO_KILOGRAMS for _ in range(bucket_count)]
        for workday_date, quantity in daily_totals.items():
            totals_by_bucket[bucket_index(workday_date)] += quantity

        points = []
        for index in range(bucket_count):
            if period == "week":
                point_start = start_date + timedelta(days=index)
                point_end = point_start
            elif period == "month":
                point_start = start_date + timedelta(days=index * 7)
                point_end = min(point_start + timedelta(days=6), today)
            elif period == "all":
                point_start = start_date.replace(year=start_date.year + index)
                point_end = min(point_start.replace(month=12, day=31), today)
            else:
                point_start = start_date.replace(month=index + 1)
                if index + 1 < 12:
                    point_end = start_date.replace(month=index + 2, day=1) - timedelta(days=1)
                else:
                    point_end = today
                point_end = min(point_end, today)

            points.append(
                {
                    "start_date": point_start,
                    "end_date": point_end,
                    "total_quantity_kg": totals_by_bucket[index],
                }
            )

        return {
            "period": period,
            "start_date": start_date,
            "end_date": today,
            "total_quantity_kg": sum(
                (point["total_quantity_kg"] for point in points),
                ZERO_KILOGRAMS,
            ),
            "points": points,
        }
