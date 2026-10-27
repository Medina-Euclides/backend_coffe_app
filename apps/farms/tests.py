from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import UserRole
from apps.farms.models import Farm, Lot
from apps.labor.models import ActivityType, Worker, Workday, WorkdayDetail

User = get_user_model()


class FarmsAPITests(APITestCase):
    """
    Pruebas automatizadas del módulo farms:
      - Creación y administración de fincas por productor.
      - Aislamiento multi-tenant entre productores.
      - Creación de lotes y validación de pertenencia a finca del productor.
      - Desactivación lógica de lotes conservando historial.
      - Manejo controlado de ProtectedError en eliminaciones de fincas y lotes.
    """

    def setUp(self):
        """Prepara productores y fincas iniciales."""
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
        self.admin = User.objects.create_superuser(
            email="admin@cafetera.com",
            password="AdminPassword123!",
            first_name="Admin",
            last_name="General",
        )

        self.farm1 = Farm.objects.create(
            id_productor=self.prod1,
            name="El Porvenir",
            location="El Tablón",
        )
        self.farm2 = Farm.objects.create(
            id_productor=self.prod2,
            name="La Esperanza",
            location="Vereda Alta",
        )

    def test_create_farm_assigns_current_producer(self):
        """Verifica que una finca creada por un productor se asigne automáticamente a su cuenta."""
        self.client.force_authenticate(user=self.prod1)
        payload = {
            "name": "Finca Nueva",
            "location": "Vereda Central",
            "description": "Finca de prueba",
        }
        res = self.client.post("/farms/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        created_farm = Farm.objects.get(id=res.data["id"])
        self.assertEqual(created_farm.id_productor, self.prod1)

    def test_prevent_assigning_farm_to_other_producer(self):
        """Verifica que un productor no pueda registrar fincas a nombre de otro productor."""
        self.client.force_authenticate(user=self.prod1)
        payload = {
            "name": "Finca Suplantada",
            "id_productor": str(self.prod2.id),
        }
        res = self.client.post("/farms/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_farm_isolation_between_producers(self):
        """Verifica que cada productor solo vea sus fincas y el administrador vea todas."""
        self.client.force_authenticate(user=self.prod1)
        res_p1 = self.client.get("/farms/")
        self.assertEqual(res_p1.status_code, status.HTTP_200_OK)
        farm_ids = [f["id"] for f in res_p1.data]
        self.assertIn(str(self.farm1.id), farm_ids)
        self.assertNotIn(str(self.farm2.id), farm_ids)

        # Acceso directo a finca ajena es denegado (404 por filtrado de queryset)
        res_direct = self.client.get(f"/farms/{self.farm2.id}/")
        self.assertEqual(res_direct.status_code, status.HTTP_404_NOT_FOUND)

        # Administrador ve todas las fincas
        self.client.force_authenticate(user=self.admin)
        res_admin = self.client.get("/farms/")
        admin_farm_ids = [f["id"] for f in res_admin.data]
        self.assertIn(str(self.farm1.id), admin_farm_ids)
        self.assertIn(str(self.farm2.id), admin_farm_ids)

    def test_create_lot_success_and_belonging_to_farm(self):
        """Verifica creación de lotes en fincas del productor."""
        self.client.force_authenticate(user=self.prod1)
        payload = {
            "id_farm": str(self.farm1.id),
            "name": "Lote 1",
            "coffee_variety": "Castillo",
            "area_m2": "2500.00",
            "is_active": True,
        }
        res = self.client.post("/farms/lots/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["name"], "Lote 1")

    def test_prevent_creating_lot_in_other_producer_farm(self):
        """Verifica que no se permita crear lotes en fincas de otros productores."""
        self.client.force_authenticate(user=self.prod1)
        payload = {
            "id_farm": str(self.farm2.id),
            "name": "Lote Intruso",
            "area_m2": "1000.00",
        }
        res = self.client.post("/farms/lots/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_deactivate_lot_preserves_record(self):
        """Verifica que un lote pueda desactivarse sin eliminarse de la base de datos (Regla 6)."""
        lot = Lot.objects.create(id_farm=self.farm1, name="Lote Desactivar", is_active=True)
        self.client.force_authenticate(user=self.prod1)

        res = self.client.patch(f"/farms/lots/{lot.id}/", {"is_active": False}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        lot.refresh_from_db()
        self.assertFalse(lot.is_active)

    def test_prevent_deleting_farm_with_lots(self):
        """Verifica que no se permita eliminar una finca si tiene lotes asociados (ProtectedError capturado)."""
        Lot.objects.create(id_farm=self.farm1, name="Lote de Protección")
        self.client.force_authenticate(user=self.prod1)

        res = self.client.delete(f"/farms/{self.farm1.id}/")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("lotes asociados", res.data["detail"])

    def test_prevent_deleting_lot_with_workday_details(self):
        """Verifica que no se permita eliminar un lote si tiene labores registradas (ProtectedError capturado)."""
        lot = Lot.objects.create(id_farm=self.farm1, name="Lote Con Labores")
        worker = Worker.objects.create(producer=self.prod1, first_name="Juan", last_name="Perez")
        act = ActivityType.objects.create(producer=self.prod1, name="Plateo")
        workday = Workday.objects.create(worker=worker, date="2026-10-20", agreed_rate="50000.00")
        WorkdayDetail.objects.create(workday=workday, activity_type=act, lot=lot)

        self.client.force_authenticate(user=self.prod1)
        res = self.client.delete(f"/farms/lots/{lot.id}/")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("is_active", res.data["detail"])
