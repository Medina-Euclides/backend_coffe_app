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

    # ------------------------------------------------------------------
    # Fincas, lotes y tipos de actividad sin conexión
    # ------------------------------------------------------------------
    def test_farm_lot_activity_created_offline_with_client_ids(self):
        farm_id, lot_id, activity_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        ops = [
            op("farm", "create", farm_id, {"name": "El Mirador", "location": "Popayán"}),
            op("lot", "create", lot_id, {"id_farm": str(farm_id), "name": "Lote Alto"}),
            op("activity_type", "create", activity_id, {"name": "Abonado", "is_harvest": False}),
            op("lot", "update", lot_id, {"is_active": False}),
        ]
        response = self.push(ops)
        self.assertEqual([r["status"] for r in response.data["results"]], ["applied"] * 4)
        farm = Farm.objects.get(pk=farm_id)
        self.assertEqual(farm.id_productor, self.user)
        self.assertFalse(Lot.objects.get(pk=lot_id).is_active)
        self.assertEqual(ActivityType.objects.get(pk=activity_id).producer, self.user)

        # Reenviar la misma cola (respuesta perdida) no duplica nada.
        response = self.push(ops)
        self.assertEqual([r["status"] for r in response.data["results"]], ["duplicate"] * 4)
        self.assertEqual(Farm.objects.filter(name="El Mirador").count(), 1)

        # Otra operación con el mismo id de registro tampoco lo duplica.
        response = self.push([op("farm", "create", farm_id, {"name": "El Mirador"})])
        self.assertEqual(response.data["results"][0]["status"], "applied")
        self.assertEqual(Farm.objects.filter(name="El Mirador").count(), 1)

    def test_activity_type_delete_offline(self):
        activity = ActivityType.objects.create(producer=self.user, name="Poda")
        response = self.push([op("activity_type", "delete", activity.id)])
        self.assertEqual(response.data["results"][0]["status"], "applied")
        self.assertFalse(ActivityType.objects.filter(pk=activity.id).exists())

    def test_cannot_create_lot_on_other_producer_farm(self):
        other_farm = Farm.objects.create(id_productor=self.other, name="Ajena")
        response = self.push([
            op("lot", "create", uuid.uuid4(), {"id_farm": str(other_farm.id), "name": "X"}),
        ])
        self.assertEqual(response.data["results"][0]["status"], "rejected")

    # ------------------------------------------------------------------
    # Liquidar y pagar sin conexión
    # ------------------------------------------------------------------
    def settle_op(self, settlement_id, ids, amount, op_id=None):
        today = str(date.today())
        return op("settlement", "settle_and_pay", settlement_id, {
            "worker": str(self.worker.id),
            "farm": str(self.farm.id),
            "start_date": today,
            "end_date": today,
            "workday_worker_ids": [],
            "harvest_record_ids": [str(ids["harvest"])],
            "date": today,
            "amount_paid": amount,
            "payment_method": "efectivo",
        }, op_id=op_id)

    def test_settle_and_pay_offline_is_atomic_and_idempotent(self):
        from apps.payroll.models import LaborPayment, Settlement

        ids, ops = self.offline_workday_ops()
        settlement_id = uuid.uuid4()
        # 35.5 kg * 1200 = 42600
        settle = self.settle_op(settlement_id, ids, "42600.00")
        response = self.push(ops + [settle])
        self.assertEqual([r["status"] for r in response.data["results"]], ["applied"] * 5)
        settlement = Settlement.objects.get(pk=settlement_id)
        self.assertEqual(settlement.status, "pagada")
        self.assertEqual(HarvestRecord.objects.get(pk=ids["harvest"]).settlement_status, "liquidado")

        # Mismo op_id -> duplicate.
        response = self.push([settle])
        self.assertEqual(response.data["results"][0]["status"], "duplicate")
        # Otro op_id con la misma liquidación -> idempotente, sin segundo pago.
        response = self.push([self.settle_op(settlement_id, ids, "42600.00")])
        self.assertEqual(response.data["results"][0]["status"], "applied")
        self.assertEqual(LaborPayment.objects.count(), 1)

    def test_same_harvest_cannot_be_paid_twice_from_two_devices(self):
        from apps.payroll.models import LaborPayment, Settlement

        ids, ops = self.offline_workday_ops()
        self.push(ops + [self.settle_op(uuid.uuid4(), ids, "42600.00")])
        other_settlement = uuid.uuid4()
        response = self.push([self.settle_op(other_settlement, ids, "42600.00")])
        self.assertEqual(response.data["results"][0]["status"], "rejected")
        self.assertFalse(Settlement.objects.filter(pk=other_settlement).exists())
        self.assertEqual(LaborPayment.objects.count(), 1)

    def test_settle_and_pay_wrong_amount_rolls_back(self):
        from apps.payroll.models import Settlement

        ids, ops = self.offline_workday_ops()
        self.push(ops)
        settlement_id = uuid.uuid4()
        response = self.push([self.settle_op(settlement_id, ids, "100.00")])
        self.assertEqual(response.data["results"][0]["status"], "rejected")
        self.assertFalse(Settlement.objects.filter(pk=settlement_id).exists())
        self.assertEqual(HarvestRecord.objects.get(pk=ids["harvest"]).settlement_status, "registrado")

    def test_pull_only_includes_unpaid_settlements(self):
        ids, ops = self.offline_workday_ops()
        self.push(ops + [self.settle_op(uuid.uuid4(), ids, "42600.00")])
        data = self.client.get("/sync/pull/").data["data"]
        self.assertEqual(data["settlements"], [])
        self.assertEqual(data["settlement_harvests"], [])
        self.assertEqual(data["payments"], [])
        paid = self.client.get("/payroll/settlements/", {"status": "pagada"}).data
        paid = paid if isinstance(paid, list) else paid["results"]
        self.assertEqual(len(paid), 1)

    def test_settle_and_pay_accepts_rounding_difference(self):
        from apps.payroll.models import LaborPayment

        ids, ops = self.offline_workday_ops()
        response = self.push(ops + [self.settle_op(uuid.uuid4(), ids, "42600.40")])
        self.assertEqual(response.data["results"][-1]["status"], "applied")
        # Se registra el total calculado por el servidor, no el enviado.
        self.assertEqual(str(LaborPayment.objects.get().amount_paid), "42600.00")
