from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import UserRole
from apps.farms.models import Farm, Lot
from apps.labor.models import (
    ActivityType,
    HarvestRecord,
    Workday,
    WorkdayDetail,
    WorkdayWorker,
    Worker,
)

User = get_user_model()


class LaborAPITests(APITestCase):
    def setUp(self):
        self.prod1 = User.objects.create_user(
            email="productor1@cafetera.com",
            password="test-password",
            first_name="Carlos",
            last_name="Restrepo",
            role=UserRole.PRODUCER,
        )
        self.prod2 = User.objects.create_user(
            email="productor2@cafetera.com",
            password="test-password",
            first_name="Pedro",
            last_name="Gomez",
            role=UserRole.PRODUCER,
        )
        self.farm1 = Farm.objects.create(id_productor=self.prod1, name="El Porvenir")
        self.farm1_b = Farm.objects.create(id_productor=self.prod1, name="La Vega")
        self.farm2 = Farm.objects.create(id_productor=self.prod2, name="La Esperanza")
        self.lot1 = Lot.objects.create(id_farm=self.farm1, name="Lote 1")
        self.inactive_lot = Lot.objects.create(
            id_farm=self.farm1,
            name="Lote inactivo",
            is_active=False,
        )
        self.lot2 = Lot.objects.create(id_farm=self.farm2, name="Lote ajeno")

        self.worker1 = Worker.objects.create(
            producer=self.prod1,
            first_name="Juan",
            last_name="Gomez",
            identification="10001",
        )
        self.worker1_other = Worker.objects.create(
            producer=self.prod1,
            first_name="Maria",
            last_name="Lopez",
            identification="10003",
        )
        self.inactive_worker = Worker.objects.create(
            producer=self.prod1,
            first_name="Inactivo",
            last_name="Perez",
            identification="10002",
            is_active=False,
        )
        self.worker2 = Worker.objects.create(
            producer=self.prod2,
            first_name="Pedro",
            last_name="Ajeno",
            identification="20001",
        )
        self.cleaning = ActivityType.objects.create(
            producer=self.prod1,
            name="Limpieza",
        )
        self.harvesting = ActivityType.objects.create(
            producer=self.prod1,
            name="Recolección",
            is_harvest=True,
        )
        self.other_activity = ActivityType.objects.create(
            producer=self.prod2,
            name="Actividad ajena",
        )

    def _create_workday(self, *, date="2026-10-20", farm=None):
        farm = farm or self.farm1
        return Workday.objects.create(
            producer=farm.id_productor,
            farm=farm,
            date=date,
        )

    def _create_participation(
        self,
        workday,
        *,
        worker=None,
        payment_mode=WorkdayWorker.PaymentMode.DAILY,
        rate="50000.00",
    ):
        return WorkdayWorker.objects.create(
            workday=workday,
            worker=worker or self.worker1,
            payment_mode=payment_mode,
            agreed_rate=Decimal(rate),
        )

    def test_worker_and_activity_creation_assign_producer(self):
        self.client.force_authenticate(user=self.prod1)
        worker_response = self.client.post(
            "/labor/workers/",
            {"first_name": "Nuevo", "last_name": "Trabajador"},
            format="json",
        )
        activity_response = self.client.post(
            "/labor/activity-types/",
            {"name": "Abonado", "is_harvest": False},
            format="json",
        )
        self.assertEqual(worker_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(activity_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Worker.objects.get(id=worker_response.data["id"]).producer, self.prod1)
        self.assertEqual(
            ActivityType.objects.get(id=activity_response.data["id"]).producer,
            self.prod1,
        )

    def test_create_workday_and_reject_duplicate_for_same_farm_and_date(self):
        self.client.force_authenticate(user=self.prod1)
        payload = {"farm": str(self.farm1.id), "date": "2026-10-20"}
        response = self.client.post("/labor/workdays/", payload, format="json")
        duplicate = self.client.post("/labor/workdays/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["producer"], self.prod1.id)
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)

    def test_same_producer_can_create_workday_for_another_farm_same_date(self):
        self.client.force_authenticate(user=self.prod1)
        first = self.client.post(
            "/labor/workdays/",
            {"farm": str(self.farm1.id), "date": "2026-10-20"},
            format="json",
        )
        second = self.client.post(
            "/labor/workdays/",
            {"farm": str(self.farm1_b.id), "date": "2026-10-20"},
            format="json",
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)

    def test_one_workday_supports_multiple_workers_with_separate_agreements(self):
        workday = self._create_workday()
        first = self._create_participation(workday, rate="50000.00")
        second = self._create_participation(
            workday,
            worker=self.worker1_other,
            payment_mode=WorkdayWorker.PaymentMode.KILOGRAM,
            rate="1200.00",
        )

        self.assertEqual(workday.participants.count(), 2)
        self.assertNotEqual(first.payment_mode, second.payment_mode)
        self.assertNotEqual(first.agreed_rate, second.agreed_rate)

    def test_workday_list_includes_participant_worker_identification(self):
        workday = self._create_workday()
        self._create_participation(workday)
        self.client.force_authenticate(user=self.prod1)

        response = self.client.get("/labor/workdays/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        self.assertEqual(
            results[0]["participants"][0]["worker_identification"],
            self.worker1.identification,
        )

    def test_update_workday_labor_updates_all_pending_participants_and_details(self):
        workday = self._create_workday()
        first = self._create_participation(workday)
        second = self._create_participation(
            workday,
            worker=self.worker1_other,
            payment_mode=WorkdayWorker.PaymentMode.KILOGRAM,
            rate="1200.00",
        )
        first_detail = WorkdayDetail.objects.create(
            workday_worker=first,
            activity_type=self.cleaning,
            lot=self.lot1,
        )
        second_detail = WorkdayDetail.objects.create(
            workday_worker=second,
            activity_type=self.harvesting,
            lot=self.lot1,
        )
        self.client.force_authenticate(user=self.prod1)

        response = self.client.patch(
            f"/labor/workdays/{workday.id}/labor/",
            {
                "activity_type": str(self.harvesting.id),
                "payment_mode": WorkdayWorker.PaymentMode.KILOGRAM,
                "agreed_rate": "1500.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        first.refresh_from_db()
        second.refresh_from_db()
        first_detail.refresh_from_db()
        second_detail.refresh_from_db()
        self.assertEqual(first.payment_mode, WorkdayWorker.PaymentMode.KILOGRAM)
        self.assertEqual(second.payment_mode, WorkdayWorker.PaymentMode.KILOGRAM)
        self.assertEqual(first.agreed_rate, Decimal("1500.00"))
        self.assertEqual(second.agreed_rate, Decimal("1500.00"))
        self.assertEqual(first_detail.activity_type, self.harvesting)
        self.assertEqual(second_detail.activity_type, self.harvesting)

    def test_update_workday_labor_rejects_journal_mode_when_pesajes_exist(self):
        workday = self._create_workday()
        participation = self._create_participation(
            workday,
            payment_mode=WorkdayWorker.PaymentMode.KILOGRAM,
            rate="1200.00",
        )
        detail = WorkdayDetail.objects.create(
            workday_worker=participation,
            activity_type=self.harvesting,
            lot=self.lot1,
        )
        HarvestRecord.objects.create(
            workday_detail=detail,
            quantity_kg=Decimal("5.000"),
            time="10:00",
        )
        self.client.force_authenticate(user=self.prod1)

        response = self.client.patch(
            f"/labor/workdays/{workday.id}/labor/",
            {
                "activity_type": str(self.cleaning.id),
                "payment_mode": WorkdayWorker.PaymentMode.DAILY,
                "agreed_rate": "55000.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        participation.refresh_from_db()
        detail.refresh_from_db()
        self.assertEqual(
            participation.payment_mode,
            WorkdayWorker.PaymentMode.KILOGRAM,
        )
        self.assertEqual(participation.agreed_rate, Decimal("1200.00"))
        self.assertEqual(detail.activity_type, self.harvesting)

    def test_update_workday_labor_rejects_closed_workday(self):
        workday = self._create_workday()
        participation = self._create_participation(workday)
        detail = WorkdayDetail.objects.create(
            workday_worker=participation,
            activity_type=self.cleaning,
            lot=self.lot1,
        )
        workday.status = Workday.Status.CLOSED
        workday.save(update_fields=["status"])
        self.client.force_authenticate(user=self.prod1)

        response = self.client.patch(
            f"/labor/workdays/{workday.id}/labor/",
            {
                "activity_type": str(self.harvesting.id),
                "payment_mode": WorkdayWorker.PaymentMode.DAILY,
                "agreed_rate": "55000.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        participation.refresh_from_db()
        detail.refresh_from_db()
        self.assertEqual(participation.agreed_rate, Decimal("50000.00"))
        self.assertEqual(detail.activity_type, self.cleaning)

    def test_workday_rejects_another_producers_farm(self):
        self.client.force_authenticate(user=self.prod1)
        response = self.client.post(
            "/labor/workdays/",
            {"farm": str(self.farm2.id), "date": "2026-10-20"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_participation_and_reject_duplicate_worker(self):
        workday = self._create_workday()
        self.client.force_authenticate(user=self.prod1)
        payload = {
            "workday": str(workday.id),
            "worker": str(self.worker1.id),
            "payment_mode": WorkdayWorker.PaymentMode.DAILY,
            "agreed_rate": "50000.00",
        }
        response = self.client.post("/labor/workday-workers/", payload, format="json")
        duplicate = self.client.post("/labor/workday-workers/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)

    def test_canceled_participation_can_be_reactivated_on_open_workday(self):
        workday = self._create_workday()
        participation = self._create_participation(workday)
        self.client.force_authenticate(user=self.prod1)
        canceled = self.client.post(
            f"/labor/workday-workers/{participation.id}/cancel/"
        )
        reactivated = self.client.post(
            f"/labor/workday-workers/{participation.id}/reactivate/"
        )

        self.assertEqual(canceled.status_code, status.HTTP_200_OK)
        self.assertEqual(reactivated.status_code, status.HTTP_200_OK)
        participation.refresh_from_db()
        self.assertEqual(
            participation.settlement_status,
            WorkdayWorker.SettlementStatus.PENDING,
        )
        self.assertEqual(workday.participants.count(), 1)

    def test_reactivation_rejects_closed_workday_or_inactive_worker(self):
        closed_workday = self._create_workday()
        closed_participation = self._create_participation(closed_workday)
        closed_workday.status = Workday.Status.CLOSED
        closed_workday.save(update_fields=["status"])
        closed_participation.settlement_status = (
            WorkdayWorker.SettlementStatus.CANCELED
        )
        closed_participation.save(update_fields=["settlement_status"])

        inactive_workday = self._create_workday(
            date="2026-10-21",
        )
        inactive_participation = self._create_participation(
            inactive_workday,
            worker=self.inactive_worker,
        )
        inactive_participation.settlement_status = (
            WorkdayWorker.SettlementStatus.CANCELED
        )
        inactive_participation.save(update_fields=["settlement_status"])

        self.client.force_authenticate(user=self.prod1)
        closed_response = self.client.post(
            f"/labor/workday-workers/{closed_participation.id}/reactivate/"
        )
        inactive_response = self.client.post(
            f"/labor/workday-workers/{inactive_participation.id}/reactivate/"
        )

        self.assertEqual(closed_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(inactive_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancellation_rejects_closed_workday(self):
        workday = self._create_workday()
        participation = self._create_participation(workday)
        workday.status = Workday.Status.CLOSED
        workday.save(update_fields=["status"])
        self.client.force_authenticate(user=self.prod1)

        response = self.client.post(
            f"/labor/workday-workers/{participation.id}/cancel/"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        participation.refresh_from_db()
        self.assertEqual(
            participation.settlement_status,
            WorkdayWorker.SettlementStatus.PENDING,
        )

    def test_participation_rejects_inactive_or_foreign_worker(self):
        workday = self._create_workday()
        self.client.force_authenticate(user=self.prod1)
        for worker in (self.inactive_worker, self.worker2):
            response = self.client.post(
                "/labor/workday-workers/",
                {
                    "workday": str(workday.id),
                    "worker": str(worker.id),
                    "payment_mode": WorkdayWorker.PaymentMode.DAILY,
                    "agreed_rate": "50000.00",
                },
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_participation_requires_positive_agreed_rate(self):
        workday = self._create_workday()
        self.client.force_authenticate(user=self.prod1)
        response = self.client.post(
            "/labor/workday-workers/",
            {
                "workday": str(workday.id),
                "worker": str(self.worker1.id),
                "payment_mode": WorkdayWorker.PaymentMode.DAILY,
                "agreed_rate": "0.00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_workday_detail_requires_matching_active_lot_and_activity_owner(self):
        workday = self._create_workday()
        participation = self._create_participation(workday)
        self.client.force_authenticate(user=self.prod1)
        valid_payload = {
            "workday_worker": str(participation.id),
            "activity_type": str(self.cleaning.id),
            "lot": str(self.lot1.id),
        }
        valid = self.client.post("/labor/workday-details/", valid_payload, format="json")
        self.assertEqual(valid.status_code, status.HTTP_201_CREATED)

        for lot in (self.inactive_lot, self.lot2):
            response = self.client.post(
                "/labor/workday-details/",
                {**valid_payload, "lot": str(lot.id)},
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        foreign_activity = self.client.post(
            "/labor/workday-details/",
            {**valid_payload, "activity_type": str(self.other_activity.id)},
            format="json",
        )
        self.assertEqual(foreign_activity.status_code, status.HTTP_400_BAD_REQUEST)

    def test_kilogram_participation_only_accepts_harvest_activity(self):
        workday = self._create_workday()
        participation = self._create_participation(
            workday,
            payment_mode=WorkdayWorker.PaymentMode.KILOGRAM,
            rate="1000.00",
        )
        self.client.force_authenticate(user=self.prod1)
        payload = {
            "workday_worker": str(participation.id),
            "activity_type": str(self.cleaning.id),
            "lot": str(self.lot1.id),
        }
        invalid = self.client.post("/labor/workday-details/", payload, format="json")
        valid = self.client.post(
            "/labor/workday-details/",
            {**payload, "activity_type": str(self.harvesting.id)},
            format="json",
        )
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(valid.status_code, status.HTTP_201_CREATED)

    def test_harvest_record_requires_harvest_activity_and_positive_quantity(self):
        workday = self._create_workday()
        participation = self._create_participation(workday)
        cleaning_detail = WorkdayDetail.objects.create(
            workday_worker=participation,
            activity_type=self.cleaning,
            lot=self.lot1,
        )
        harvest_detail = WorkdayDetail.objects.create(
            workday_worker=participation,
            activity_type=self.harvesting,
            lot=self.lot1,
        )
        self.client.force_authenticate(user=self.prod1)
        invalid_activity = self.client.post(
            "/labor/harvest-records/",
            {
                "workday_detail": str(cleaning_detail.id),
                "quantity_kg": "5.000",
                "time": "10:00:00",
            },
            format="json",
        )
        invalid_quantity = self.client.post(
            "/labor/harvest-records/",
            {
                "workday_detail": str(harvest_detail.id),
                "quantity_kg": "0.000",
                "time": "10:00:00",
            },
            format="json",
        )
        valid = self.client.post(
            "/labor/harvest-records/",
            {
                "workday_detail": str(harvest_detail.id),
                "quantity_kg": "5.250",
                "time": "10:00:00",
            },
            format="json",
        )
        self.assertEqual(invalid_activity.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(invalid_quantity.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(valid.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Decimal(valid.data["quantity_kg"]), Decimal("5.250"))

    def test_deleting_worker_or_activity_with_history_is_rejected(self):
        workday = self._create_workday()
        participation = self._create_participation(workday)
        WorkdayDetail.objects.create(
            workday_worker=participation,
            activity_type=self.cleaning,
            lot=self.lot1,
        )
        self.client.force_authenticate(user=self.prod1)
        worker_response = self.client.delete(f"/labor/workers/{self.worker1.id}/")
        activity_response = self.client.delete(
            f"/labor/activity-types/{self.cleaning.id}/"
        )
        self.assertEqual(worker_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(activity_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_database_rejects_invalid_quantity_and_rate(self):
        workday = self._create_workday()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                WorkdayWorker.objects.create(
                    workday=workday,
                    worker=self.worker1,
                    agreed_rate=Decimal("0"),
                )

        participation = self._create_participation(workday)
        detail = WorkdayDetail.objects.create(
            workday_worker=participation,
            activity_type=self.harvesting,
            lot=self.lot1,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                HarvestRecord.objects.create(
                    workday_detail=detail,
                    quantity_kg=Decimal("0"),
                    time="10:00",
                )
