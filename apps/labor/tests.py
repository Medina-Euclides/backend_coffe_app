from decimal import Decimal
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import UserRole
from apps.farms.models import Farm, Lot
from apps.labor.models import ActivityType, HarvestRecord, Worker, Workday, WorkdayDetail

User = get_user_model()


class LaborAPITests(APITestCase):
    """
    Pruebas automatizadas del módulo labor:
      - Registro de trabajadores y tipos de actividad (con y sin 'producer' explícito).
      - Validación de identificación única y conservación histórica de trabajadores.
      - Aislamiento multi-tenant en jornadas, detalles de labor y recolecciones.
      - Validación de lote activo y concordancia de modalidad de pago (jornal vs kg).
      - Validación de actividades de recolección (is_harvest=True) para pesajes de café.
      - Manejo controlado de ProtectedError en eliminaciones de trabajadores y actividades.
    """

    def setUp(self):
        """Prepara productores, fincas, lotes y trabajadores de prueba."""
        self.prod1 = User.objects.create_user(
            email="productor1@cafetera.com",
            password="PasswordProd1_123!",
            first_name="Carlos",
            last_name="Restrepo",
            role=UserRole.PRODUCER,
        )
        self.prod2 = User.objects.create_user(
            email="productor2@cafetera.com",
            password="PasswordProd2_123!",
            first_name="Pedro",
            last_name="Gomez",
            role=UserRole.PRODUCER,
        )

        self.farm1 = Farm.objects.create(id_productor=self.prod1, name="El Porvenir")
        self.farm2 = Farm.objects.create(id_productor=self.prod2, name="La Esperanza")

        self.lot1 = Lot.objects.create(id_farm=self.farm1, name="Lote 1", is_active=True)
        self.lot_inactive = Lot.objects.create(id_farm=self.farm1, name="Lote Inactivo", is_active=False)
        self.lot2 = Lot.objects.create(id_farm=self.farm2, name="Lote Pedro", is_active=True)

        self.worker1 = Worker.objects.create(
            producer=self.prod1,
            first_name="Juan",
            last_name="Gomez",
            identification="10001",
            is_active=True,
        )
        self.worker_inactive = Worker.objects.create(
            producer=self.prod1,
            first_name="Inactivo",
            last_name="Perez",
            identification="10002",
            is_active=False,
        )
        self.worker_prod2 = Worker.objects.create(
            producer=self.prod2,
            first_name="Trabajador",
            last_name="Ajeno",
            identification="99999",
            is_active=True,
        )

        self.act_limpieza = ActivityType.objects.create(
            producer=self.prod1,
            name="Limpieza",
            is_harvest=False,
        )
        self.act_recoleccion = ActivityType.objects.create(
            producer=self.prod1,
            name="Recolección",
            is_harvest=True,
        )
        self.act_prod2 = ActivityType.objects.create(
            producer=self.prod2,
            name="Abonado Ajeno",
            is_harvest=False,
        )

    def test_create_worker_auto_assigns_producer(self):
        """Verifica que el productor no esté obligado a enviar su UUID al crear un trabajador."""
        self.client.force_authenticate(user=self.prod1)
        payload = {
            "first_name": "Nuevo",
            "last_name": "Trabajador",
            "identification": "10003",
            "phone": "3101234567",
        }
        res = self.client.post("/labor/workers/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        worker = Worker.objects.get(id=res.data["id"])
        self.assertEqual(worker.producer, self.prod1)

    def test_create_worker_duplicate_identification_rejected(self):
        """Verifica rechazo de identificación duplicada de trabajador."""
        self.client.force_authenticate(user=self.prod1)
        payload = {
            "first_name": "Duplicado",
            "last_name": "Gomez",
            "identification": "10001",
        }
        res = self.client.post("/labor/workers/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("identification", res.data)

    def test_deactivate_worker_preserves_record(self):
        """Verifica que un trabajador pueda desactivarse conservando su registro histórico."""
        self.client.force_authenticate(user=self.prod1)
        res = self.client.patch(f"/labor/workers/{self.worker1.id}/", {"is_active": False}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.worker1.refresh_from_db()
        self.assertFalse(self.worker1.is_active)

    def test_create_activity_type_auto_assigns_producer(self):
        """Verifica creación de tipo de actividad sin requerir el UUID del productor en el body."""
        self.client.force_authenticate(user=self.prod1)
        payload = {
            "name": "Ahoyado",
            "description": "Preparación de hoyos",
            "is_harvest": False,
        }
        res = self.client.post("/labor/activity-types/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        activity = ActivityType.objects.get(id=res.data["id"])
        self.assertEqual(activity.producer, self.prod1)

    def test_create_workday_success(self):
        """Verifica creación exitosa de una jornada laboral."""
        self.client.force_authenticate(user=self.prod1)
        payload = {
            "worker": str(self.worker1.id),
            "date": "2026-10-20",
            "payment_mode": "jornal",
            "agreed_rate": "50000.00",
        }
        res = self.client.post("/labor/workdays/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    def test_create_workday_duplicate_worker_date_rejected(self):
        """Verifica restricción de unicidad de jornada por trabajador y fecha."""
        Workday.objects.create(worker=self.worker1, date="2026-10-20", agreed_rate="50000.00")
        self.client.force_authenticate(user=self.prod1)
        payload = {
            "worker": str(self.worker1.id),
            "date": "2026-10-20",
            "payment_mode": "jornal",
            "agreed_rate": "50000.00",
        }
        res = self.client.post("/labor/workdays/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_workday_inactive_worker_rejected(self):
        """Verifica que no se puedan crear jornadas para trabajadores inactivos."""
        self.client.force_authenticate(user=self.prod1)
        payload = {
            "worker": str(self.worker_inactive.id),
            "date": "2026-10-20",
            "payment_mode": "jornal",
            "agreed_rate": "50000.00",
        }
        res = self.client.post("/labor/workdays/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("worker", res.data)

    def test_create_workday_other_producer_worker_rejected(self):
        """Verifica que no se pueda crear una jornada con un trabajador de otro productor."""
        self.client.force_authenticate(user=self.prod1)
        payload = {
            "worker": str(self.worker_prod2.id),
            "date": "2026-10-25",
            "payment_mode": "jornal",
            "agreed_rate": "50000.00",
        }
        res = self.client.post("/labor/workdays/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_workday_detail_success(self):
        """Verifica asociación de detalle de jornada con lote y actividad propia."""
        workday = Workday.objects.create(worker=self.worker1, date="2026-10-21", agreed_rate="50000.00")
        self.client.force_authenticate(user=self.prod1)
        payload = {
            "workday": str(workday.id),
            "activity_type": str(self.act_limpieza.id),
            "lot": str(self.lot1.id),
        }
        res = self.client.post("/labor/workday-details/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    def test_create_workday_detail_inactive_lot_rejected(self):
        """Verifica que no se puedan asociar labores a lotes inactivos."""
        workday = Workday.objects.create(worker=self.worker1, date="2026-10-21", agreed_rate="50000.00")
        self.client.force_authenticate(user=self.prod1)
        payload = {
            "workday": str(workday.id),
            "activity_type": str(self.act_limpieza.id),
            "lot": str(self.lot_inactive.id),
        }
        res = self.client.post("/labor/workday-details/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("lot", res.data)

    def test_create_workday_detail_other_producer_lot_rejected(self):
        """Verifica que no se permita vincular lotes pertenecientes a fincas de otro productor."""
        workday = Workday.objects.create(worker=self.worker1, date="2026-10-21", agreed_rate="50000.00")
        self.client.force_authenticate(user=self.prod1)
        payload = {
            "workday": str(workday.id),
            "activity_type": str(self.act_limpieza.id),
            "lot": str(self.lot2.id),
        }
        res = self.client.post("/labor/workday-details/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_workday_detail_kilogram_requires_harvest_activity(self):
        """Verifica que las jornadas con modalidad por kilogramo exijan actividades de recolección."""
        workday_kg = Workday.objects.create(
            worker=self.worker1,
            date="2026-10-22",
            payment_mode=Workday.PaymentMode.KILOGRAM,
            agreed_rate="1000.00",
        )
        self.client.force_authenticate(user=self.prod1)

        # Intentar con actividad de limpieza (no cosecha) -> Debe fallar
        payload_invalid = {
            "workday": str(workday_kg.id),
            "activity_type": str(self.act_limpieza.id),
            "lot": str(self.lot1.id),
        }
        res_invalid = self.client.post("/labor/workday-details/", payload_invalid, format="json")
        self.assertEqual(res_invalid.status_code, status.HTTP_400_BAD_REQUEST)

        # Con actividad de recolección -> Debe tener éxito
        payload_valid = {
            "workday": str(workday_kg.id),
            "activity_type": str(self.act_recoleccion.id),
            "lot": str(self.lot1.id),
        }
        res_valid = self.client.post("/labor/workday-details/", payload_valid, format="json")
        self.assertEqual(res_valid.status_code, status.HTTP_201_CREATED)

    def test_create_harvest_record_success(self):
        """Verifica registro exitoso de recolección en kilogramos."""
        workday = Workday.objects.create(worker=self.worker1, date="2026-10-23", agreed_rate="1000.00")
        detail = WorkdayDetail.objects.create(workday=workday, activity_type=self.act_recoleccion, lot=self.lot1)

        self.client.force_authenticate(user=self.prod1)
        payload = {
            "workday_detail": str(detail.id),
            "quantity_kg": "25.500",
            "time": "11:30:00",
        }
        res = self.client.post("/labor/harvest-records/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Decimal(str(res.data["quantity_kg"])), Decimal("25.500"))

    def test_create_harvest_record_on_non_harvest_activity_rejected(self):
        """Verifica que se impida registrar recolección en labores que no son de cosecha (is_harvest=False)."""
        workday = Workday.objects.create(worker=self.worker1, date="2026-10-23", agreed_rate="50000.00")
        detail_limpieza = WorkdayDetail.objects.create(workday=workday, activity_type=self.act_limpieza, lot=self.lot1)

        self.client.force_authenticate(user=self.prod1)
        payload = {
            "workday_detail": str(detail_limpieza.id),
            "quantity_kg": "15.000",
            "time": "10:00:00",
        }
        res = self.client.post("/labor/harvest-records/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("workday_detail", res.data)

    def test_create_harvest_record_other_producer_detail_rejected(self):
        """Verifica que un productor no pueda registrar pesajes en jornadas de otro productor."""
        workday_p1 = Workday.objects.create(worker=self.worker1, date="2026-10-23", agreed_rate="1000.00")
        detail_p1 = WorkdayDetail.objects.create(workday=workday_p1, activity_type=self.act_recoleccion, lot=self.lot1)

        # Productor 2 intenta registrar pesaje en jornada de Productor 1
        self.client.force_authenticate(user=self.prod2)
        payload = {
            "workday_detail": str(detail_p1.id),
            "quantity_kg": "10.000",
            "time": "14:00:00",
        }
        res = self.client.post("/labor/harvest-records/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_prevent_deleting_worker_with_workdays(self):
        """Verifica que no se permita eliminar un trabajador con jornadas (ProtectedError capturado con 400)."""
        Workday.objects.create(worker=self.worker1, date="2026-10-24", agreed_rate="50000.00")
        self.client.force_authenticate(user=self.prod1)

        res = self.client.delete(f"/labor/workers/{self.worker1.id}/")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("is_active", res.data["detail"])

    def test_prevent_deleting_activity_type_with_details(self):
        """Verifica que no se permita eliminar un tipo de actividad en uso (ProtectedError capturado con 400)."""
        workday = Workday.objects.create(worker=self.worker1, date="2026-10-24", agreed_rate="50000.00")
        WorkdayDetail.objects.create(workday=workday, activity_type=self.act_limpieza, lot=self.lot1)

        self.client.force_authenticate(user=self.prod1)
        res = self.client.delete(f"/labor/activity-types/{self.act_limpieza.id}/")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
