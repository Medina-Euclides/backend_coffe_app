import uuid
from datetime import date

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.farms.models import Farm, Lot
from apps.labor.models import ActivityType, HarvestRecord, Workday, Worker

User = get_user_model()


def op(entity, action, object_id, data=None, op_id=None):
    return {
        "op_id": str(op_id or uuid.uuid4()),
        "entity": entity,
        "action": action,
        "object_id": str(object_id),
        "data": data or {},
        "client_ts": "2026-11-06T08:00:00Z",
    }


class SyncTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="p@finca.co", password="x12345678", first_name="P", last_name="R"
        )
        self.other = User.objects.create_user(
            email="o@finca.co", password="x12345678", first_name="O", last_name="T"
        )
        self.farm = Farm.objects.create(id_productor=self.user, name="La Esperanza")
        self.lot = Lot.objects.create(id_farm=self.farm, name="Lote 1")
        self.worker = Worker.objects.create(producer=self.user, first_name="Ana", last_name="Gómez")
        self.harvest = ActivityType.objects.create(
            producer=self.user, name="Recolección", is_harvest=True
        )
        self.client.force_authenticate(self.user)

    def offline_workday_ops(self):
        ids = {k: uuid.uuid4() for k in ("workday", "ww", "detail", "harvest")}
        ops = [
            op("workday", "create", ids["workday"], {"farm": str(self.farm.id), "date": str(date.today())}),
            op("workday_worker", "create", ids["ww"], {
                "workday": str(ids["workday"]), "worker": str(self.worker.id),
                "payment_mode": "kg", "agreed_rate": "1200",
            }),
            op("workday_detail", "create", ids["detail"], {
                "workday_worker": str(ids["ww"]), "activity_type": str(self.harvest.id),
                "lot": str(self.lot.id),
            }),
            op("harvest_record", "create", ids["harvest"], {
                "workday_detail": str(ids["detail"]), "quantity_kg": "35.5", "time": "10:30",
            }),
        ]
        return ids, ops

    def push(self, operations):
        return self.client.post("/sync/push/", {"operations": operations}, format="json")

    def test_push_applies_chain_with_client_ids(self):
        ids, ops = self.offline_workday_ops()
        response = self.push(ops)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([r["status"] for r in response.data["results"]], ["applied"] * 4)
        workday = Workday.objects.get(pk=ids["workday"])
        self.assertEqual(workday.producer, self.user)
        self.assertTrue(HarvestRecord.objects.filter(pk=ids["harvest"]).exists())

    def test_push_is_idempotent(self):
        _, ops = self.offline_workday_ops()
        self.push(ops)
        response = self.push(ops)
        self.assertEqual([r["status"] for r in response.data["results"]], ["duplicate"] * 4)
        self.assertEqual(HarvestRecord.objects.count(), 1)

    def test_closed_workday_rejects_harvest(self):
        ids, ops = self.offline_workday_ops()
        self.push(ops[:3])
        Workday.objects.filter(pk=ids["workday"]).update(status="cerrada")
        response = self.push(ops[3:])
        self.assertEqual(response.data["results"][0]["status"], "rejected")
        self.assertFalse(HarvestRecord.objects.exists())

    def test_actions_close_and_cancel(self):
        ids, ops = self.offline_workday_ops()
        response = self.push(ops + [
            op("harvest_record", "cancel", ids["harvest"]),
            op("workday", "close", ids["workday"]),
        ])
        self.assertEqual(response.data["results"][-1]["status"], "applied")
        self.assertEqual(HarvestRecord.objects.get(pk=ids["harvest"]).settlement_status, "anulado")
        self.assertEqual(Workday.objects.get(pk=ids["workday"]).status, "cerrada")

    def test_cannot_touch_other_producer_data(self):
        other_farm = Farm.objects.create(id_productor=self.other, name="Ajena")
        response = self.push([
            op("workday", "create", uuid.uuid4(), {"farm": str(other_farm.id), "date": str(date.today())}),
            op("worker", "update", self.worker.id, {"first_name": "Ok"}),
        ])
        self.assertEqual(response.data["results"][0]["status"], "rejected")
        self.assertEqual(response.data["results"][1]["status"], "applied")
        self.client.force_authenticate(self.other)
        response = self.push([op("worker", "update", self.worker.id, {"first_name": "Hack"})])
        self.assertEqual(response.data["results"][0]["status"], "rejected")
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.first_name, "Ok")

    def test_unsupported_operation(self):
        response = self.push([op("farm", "delete", self.farm.id)])
        self.assertEqual(response.data["results"][0]["status"], "rejected")

    def test_pull_snapshot_only_own_data(self):
        Farm.objects.create(id_productor=self.other, name="Ajena")
        _, ops = self.offline_workday_ops()
        self.push(ops)
        response = self.client.get("/sync/pull/")
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(len(data["farms"]), 1)
        self.assertEqual(len(data["workdays"]), 1)
        self.assertEqual(len(data["workdays"][0]["participants"][0]["details"][0]["harvest_records"]), 1)
        self.assertIn("server_time", response.data)

    def test_ping_without_auth(self):
        self.client.force_authenticate(None)
        response = self.client.get("/sync/ping/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["ok"])
