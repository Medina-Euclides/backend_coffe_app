from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.farms.models import Farm, Lot
from apps.finance.models import OperatingExpense
from apps.labor.models import (
    ActivityType,
    HarvestRecord,
    Workday,
    WorkdayDetail,
    WorkdayWorker,
    Worker,
)
from apps.production.models import Sale

User = get_user_model()


class AnalyticsSummaryTests(APITestCase):
    def setUp(self):
        self.producer = User.objects.create_user(
            email="analytics@example.com",
            password="test-password",
            first_name="Ana",
            last_name="Café",
            role="PRODUCER",
        )
        self.other_producer = User.objects.create_user(
            email="other-analytics@example.com",
            password="test-password",
            first_name="Luis",
            last_name="Pérez",
            role="PRODUCER",
        )
        self.farm = Farm.objects.create(
            id_productor=self.producer,
            name="Finca principal",
        )
        self.other_farm = Farm.objects.create(
            id_productor=self.other_producer,
            name="Finca ajena",
        )
        self.lot = Lot.objects.create(
            id_farm=self.farm,
            name="Lote con producción",
            plant_count=850,
        )
        self.empty_lot = Lot.objects.create(
            id_farm=self.farm,
            name="Lote sin producción",
        )
        self.other_lot = Lot.objects.create(
            id_farm=self.other_farm,
            name="Lote de otra finca",
        )
        self.worker = Worker.objects.create(
            producer=self.producer,
            first_name="Juan",
            last_name="Gómez",
        )
        self.other_worker = Worker.objects.create(
            producer=self.other_producer,
            first_name="Pedro",
            last_name="Díaz",
        )
        self.harvest_activity = ActivityType.objects.create(
            producer=self.producer,
            name="Recolección",
            is_harvest=True,
        )
        self.other_harvest_activity = ActivityType.objects.create(
            producer=self.other_producer,
            name="Recolección",
            is_harvest=True,
        )

    def test_summary_aggregates_finances_and_excludes_other_farms(self):
        OperatingExpense.objects.create(
            farm=self.farm,
            date=date(2026, 10, 4),
            concept="Fertilizante",
            amount=Decimal("120000.00"),
            category=OperatingExpense.Category.INPUTS,
        )
        OperatingExpense.objects.create(
            farm=self.farm,
            date=date(2026, 10, 5),
            concept="Mano de obra",
            amount=Decimal("50000.00"),
            category=OperatingExpense.Category.LABOR,
        )
        OperatingExpense.objects.create(
            farm=self.other_farm,
            date=date(2026, 10, 5),
            concept="Gasto de otra finca",
            amount=Decimal("900000.00"),
            category=OperatingExpense.Category.INPUTS,
        )
        Sale.objects.create(
            farm=self.farm,
            sale_date=date(2026, 10, 6),
            coffee_type=Sale.CoffeeType.PERGAMINO,
            quantity_kg=Decimal("100.00"),
            unit_price=Decimal("10000.00"),
            total_amount=Decimal("1000000.00"),
        )
        Sale.objects.create(
            farm=self.farm,
            sale_date=date(2026, 10, 7),
            coffee_type=Sale.CoffeeType.PASILLA,
            quantity_kg=Decimal("100.00"),
            unit_price=Decimal("10000.00"),
            total_amount=Decimal("1000000.00"),
            is_active=False,
        )
        Sale.objects.create(
            farm=self.other_farm,
            sale_date=date(2026, 10, 8),
            coffee_type=Sale.CoffeeType.PERGAMINO,
            quantity_kg=Decimal("100.00"),
            unit_price=Decimal("10000.00"),
            total_amount=Decimal("1000000.00"),
        )

        self.client.force_authenticate(user=self.producer)
        response = self.client.get("/analytics/summary/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        category_totals = {
            item["category"]: Decimal(item["total_amount"])
            for item in response.data["expenses_by_category"]
        }
        self.assertEqual(
            category_totals[OperatingExpense.Category.INPUTS],
            Decimal("120000.00"),
        )
        self.assertEqual(
            category_totals[OperatingExpense.Category.LABOR],
            Decimal("50000.00"),
        )
        self.assertEqual(
            Decimal(response.data["financial_summary"]["sales_income"]),
            Decimal("1000000.00"),
        )
        self.assertEqual(
            Decimal(response.data["financial_summary"]["total_expenses"]),
            Decimal("170000.00"),
        )
        self.assertEqual(
            Decimal(response.data["financial_summary"]["net_income"]),
            Decimal("830000.00"),
        )
        self.assertEqual(
            {item["lot_name"] for item in response.data["production_by_lot"]},
            {self.lot.name, self.empty_lot.name},
        )

    def test_summary_supports_farm_filter_and_protects_farm_ownership(self):
        self.client.force_authenticate(user=self.producer)

        response = self.client.get(
            f"/analytics/summary/?farm_id={self.farm.id}"
        )
        forbidden_response = self.client.get(
            f"/analytics/summary/?farm_id={self.other_farm.id}"
        )
        invalid_response = self.client.get("/analytics/summary/?farm_id=no-es-uuid")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["farm_id"], str(self.farm.id))
        self.assertEqual(response.data["farm_name"], self.farm.name)
        self.assertEqual(
            forbidden_response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(invalid_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_production_is_reported_by_lot_and_current_calendar_period(self):
        today = timezone.localdate()
        self._create_harvest(
            farm=self.farm,
            lot=self.lot,
            worker=self.worker,
            activity=self.harvest_activity,
            workday_date=today,
            quantity=Decimal("10.250"),
        )
        previous_year = date(today.year - 1, 12, 31)
        self._create_harvest(
            farm=self.farm,
            lot=self.lot,
            worker=self.worker,
            activity=self.harvest_activity,
            workday_date=previous_year,
            quantity=Decimal("4.500"),
        )
        self._create_harvest(
            farm=self.other_farm,
            lot=self.other_lot,
            worker=self.other_worker,
            activity=self.other_harvest_activity,
            workday_date=today,
            quantity=Decimal("99.000"),
        )
        self.client.force_authenticate(user=self.producer)

        response = self.client.get("/analytics/summary/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        lots = {
            item["lot_id"]: item for item in response.data["production_by_lot"]
        }
        self.assertEqual(
            Decimal(lots[str(self.lot.id)]["total_quantity_kg"]),
            Decimal("14.750"),
        )
        self.assertEqual(lots[str(self.lot.id)]["plant_count"], 850)
        self.assertEqual(
            Decimal(lots[str(self.empty_lot.id)]["total_quantity_kg"]),
            Decimal("0.000"),
        )

        periods = response.data["production_by_period"]
        self.assertEqual(
            Decimal(periods["week"]["total_quantity_kg"]),
            Decimal("10.250"),
        )
        self.assertEqual(
            Decimal(periods["month"]["total_quantity_kg"]),
            Decimal("10.250"),
        )
        self.assertEqual(
            Decimal(periods["year"]["total_quantity_kg"]),
            Decimal("10.250"),
        )
        self.assertEqual(periods["week"]["start_date"], (
            today - timedelta(days=today.weekday())
        ).isoformat())
        self.assertEqual(periods["month"]["end_date"], today.isoformat())
        self.assertEqual(periods["year"]["end_date"], today.isoformat())
        self.assertEqual(response.data["production_series"]["period"], "month")
        self.assertEqual(
            Decimal(response.data["production_series"]["total_quantity_kg"]),
            Decimal("10.250"),
        )
        self.assertEqual(
            Decimal(
                response.data["production_series"]["points"][0][
                    "total_quantity_kg"
                ]
            ),
            Decimal("10.250"),
        )

        year_response = self.client.get("/analytics/summary/?period=year")
        self.assertEqual(year_response.status_code, status.HTTP_200_OK)
        self.assertEqual(year_response.data["production_series"]["period"], "year")
        self.assertEqual(
            len(year_response.data["production_series"]["points"]),
            today.month,
        )
        self.assertEqual(
            Decimal(year_response.data["production_series"]["total_quantity_kg"]),
            Decimal("10.250"),
        )

        invalid_period_response = self.client.get(
            "/analytics/summary/?period=quarter"
        )
        self.assertEqual(
            invalid_period_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_summary_requires_authentication(self):
        response = self.client.get("/analytics/summary/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @staticmethod
    def _create_harvest(*, farm, lot, worker, activity, workday_date, quantity):
        workday, _ = Workday.objects.get_or_create(
            producer=worker.producer,
            farm=farm,
            date=workday_date,
        )
        participation, _ = WorkdayWorker.objects.get_or_create(
            worker=worker,
            workday=workday,
            defaults={"agreed_rate": Decimal("50000.00")},
        )
        detail = WorkdayDetail.objects.create(
            workday_worker=participation,
            activity_type=activity,
            lot=lot,
        )
        return HarvestRecord.objects.create(
            workday_detail=detail,
            quantity_kg=quantity,
            time="10:00",
        )
