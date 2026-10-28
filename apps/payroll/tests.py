from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import UserRole
from apps.farms.models import Farm, Lot
from apps.labor.models import (
    ActivityType,
    HarvestRecord,
    Worker,
    Workday,
    WorkdayDetail,
)
from apps.payroll.models import (
    LaborPayment,
    Settlement,
    SettlementDetailHarvest,
    SettlementDetailWorkday,
)

User = get_user_model()


class PayrollAPITests(APITestCase):
    """
    Pruebas automatizadas del módulo payroll:
      - Creación y consulta de liquidaciones del productor.
      - Aislamiento multi-tenant (trabajadores, fincas, liquidaciones).
      - Una única liquidación abierta por trabajador (SRS módulo 7, regla 4).
      - Periodo válido y coherencia trabajador/finca.
      - Añadir jornadas por jornal y pesajes por kilogramo mediante servicios.
      - Rechazo de duplicados: un registro solo puede liquidarse una vez.
      - Cierre de liquidación: cálculo del total, conservación de tarifas y
        actualización de estados de las jornadas/recolecciones.
      - Pago exacto, sin pagos parciales ni dobles pagos.
      - Endpoints de detalles y pagos son de solo lectura (integridad de datos).
      - Liquidaciones cerradas/pagadas no se pueden modificar ni eliminar.
      - Permisos de acceso a liquidaciones, detalles y pagos.
    """

    def setUp(self):
        """Prepara productores, fincas, lotes, trabajadores y actividades."""
        self.prod1 = User.objects.create_user(
            email="productor1@payroll.com",
            password="PasswordProd1_123!",
            first_name="Carlos",
            last_name="Restrepo",
            role=UserRole.PRODUCER,
        )
        self.prod2 = User.objects.create_user(
            email="productor2@payroll.com",
            password="PasswordProd2_123!",
            first_name="Pedro",
            last_name="Gomez",
            role=UserRole.PRODUCER,
        )
        self.admin = User.objects.create_superuser(
            email="admin@payroll.com",
            password="AdminPassword123!",
            first_name="Admin",
            last_name="General",
        )

        self.farm1 = Farm.objects.create(id_productor=self.prod1, name="El Porvenir")
        self.farm1_alt = Farm.objects.create(id_productor=self.prod1, name="La Esperanza")
        self.farm2 = Farm.objects.create(id_productor=self.prod2, name="Finca Ajena")

        self.lot1 = Lot.objects.create(id_farm=self.farm1, name="Lote 1", is_active=True)
        self.lot1_alt = Lot.objects.create(id_farm=self.farm1_alt, name="Lote Alterno", is_active=True)
        self.lot2 = Lot.objects.create(id_farm=self.farm2, name="Lote Ajeno", is_active=True)

        self.worker1 = Worker.objects.create(
            producer=self.prod1,
            first_name="Juan",
            last_name="Gomez",
            identification="10001",
            is_active=True,
        )
        self.worker2 = Worker.objects.create(
            producer=self.prod1,
            first_name="Pedro",
            last_name="Diaz",
            identification="10002",
            is_active=True,
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

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def _create_workday(
        self,
        *,
        worker=None,
        date="2026-10-20",
        payment_mode=Workday.PaymentMode.DAILY,
        rate="50000.00",
        activity=None,
        lot=None,
    ):
        """Crea una jornada con su detalle (actividad + lote)."""
        worker = worker or self.worker1
        if activity is None:
            activity = (
                self.act_recoleccion
                if payment_mode == Workday.PaymentMode.KILOGRAM
                else self.act_limpieza
            )
        workday = Workday.objects.create(
            worker=worker,
            date=date,
            payment_mode=payment_mode,
            agreed_rate=Decimal(rate),
        )
        WorkdayDetail.objects.create(
            workday=workday,
            activity_type=activity,
            lot=lot or self.lot1,
        )
        return workday

    def _create_harvest(self, workday, kg="10.000", time="10:00:00"):
        """Crea un registro de recolección sobre la primera labor de la jornada."""
        detail = workday.details.first()
        return HarvestRecord.objects.create(
            workday_detail=detail,
            quantity_kg=Decimal(kg),
            time=time,
        )

    def _create_settlement(
        self,
        *,
        worker=None,
        farm=None,
        start_date="2026-10-01",
        end_date="2026-10-31",
        status_value=Settlement.Status.OPEN,
    ):
        """Crea una liquidación directamente en base de datos."""
        return Settlement.objects.create(
            worker=worker or self.worker1,
            farm=farm or self.farm1,
            start_date=start_date,
            end_date=end_date,
            status=status_value,
        )

    def _create_closed_settlement_with_payment(self, amount="50000.00"):
        """Crea una liquidación cerrada y pagada con su detalle y pago."""
        settlement = self._create_settlement(status_value=Settlement.Status.CLOSED)
        workday = self._create_workday(date="2026-10-20")
        SettlementDetailWorkday.objects.create(
            settlement=settlement,
            workday=workday,
            applied_daily_rate=Decimal("50000.00"),
            paid_amount=Decimal(amount),
        )
        settlement.total_calculated = Decimal(amount)
        settlement.save(update_fields=["total_calculated"])
        payment = LaborPayment.objects.create(
            settlement=settlement,
            date="2026-11-01",
            amount_paid=Decimal(amount),
            payment_method=LaborPayment.PaymentMethod.CASH,
        )
        settlement.status = Settlement.Status.PAID
        settlement.save(update_fields=["status"])
        return settlement, payment

    # ------------------------------------------------------------------
    # CREACIÓN DE LIQUIDACIONES
    # ------------------------------------------------------------------

    def test_create_settlement_success(self):
        """Crea una liquidación abierta para el trabajador y la finca propios."""
        self.client.force_authenticate(user=self.prod1)
        response = self.client.post(
            "/payroll/settlements/",
            {
                "worker": str(self.worker1.id),
                "farm": str(self.farm1.id),
                "start_date": "2026-10-01",
                "end_date": "2026-10-31",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], Settlement.Status.OPEN)
        self.assertEqual(Decimal(response.data["total_calculated"]), Decimal("0.00"))

    def test_create_settlement_requires_authentication(self):
        """Sin token JWT no se puede crear una liquidación."""
        response = self.client.post(
            "/payroll/settlements/",
            {
                "worker": str(self.worker1.id),
                "farm": str(self.farm1.id),
                "start_date": "2026-10-01",
                "end_date": "2026-10-31",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_settlement_missing_required_fields(self):
        """Rechaza la creación si faltan campos obligatorios."""
        self.client.force_authenticate(user=self.prod1)
        response = self.client.post("/payroll/settlements/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("worker", response.data)
        self.assertIn("farm", response.data)
        self.assertIn("start_date", response.data)
        self.assertIn("end_date", response.data)

    def test_create_settlement_rejects_other_producer_worker(self):
        """Un productor no puede usar el trabajador de otro productor."""
        self.client.force_authenticate(user=self.prod1)
        response = self.client.post(
            "/payroll/settlements/",
            {
                "worker": str(self.worker_prod2.id),
                "farm": str(self.farm1.id),
                "start_date": "2026-10-01",
                "end_date": "2026-10-31",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("worker", response.data)

    def test_create_settlement_rejects_other_producer_farm(self):
        """Un productor no puede usar una finca de otro productor."""
        self.client.force_authenticate(user=self.prod1)
        response = self.client.post(
            "/payroll/settlements/",
            {
                "worker": str(self.worker1.id),
                "farm": str(self.farm2.id),
                "start_date": "2026-10-01",
                "end_date": "2026-10-31",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("farm", response.data)

    def test_create_settlement_rejects_mismatched_worker_and_farm_as_admin(self):
        """El administrador tampoco puede mezclar trabajador y finca de productores distintos."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            "/payroll/settlements/",
            {
                "worker": str(self.worker_prod2.id),
                "farm": str(self.farm1.id),
                "start_date": "2026-10-01",
                "end_date": "2026-10-31",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("farm", response.data)

    def test_create_settlement_rejects_end_date_before_start_date(self):
        """Rechaza periodos inválidos (fecha fin anterior a la fecha inicio)."""
        self.client.force_authenticate(user=self.prod1)
        response = self.client.post(
            "/payroll/settlements/",
            {
                "worker": str(self.worker1.id),
                "farm": str(self.farm1.id),
                "start_date": "2026-10-31",
                "end_date": "2026-10-01",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("end_date", response.data)

    def test_create_second_open_settlement_for_same_worker_rejected(self):
        """
        Regla 4 (SRS módulo 7): un trabajador solo puede tener una liquidación
        abierta a la vez, incluso si es en otra finca del mismo productor.
        """
        self._create_settlement(farm=self.farm1)
        self.client.force_authenticate(user=self.prod1)
        response = self.client.post(
            "/payroll/settlements/",
            {
                "worker": str(self.worker1.id),
                "farm": str(self.farm1_alt.id),
                "start_date": "2026-11-01",
                "end_date": "2026-11-30",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("worker", response.data)

    def test_admin_can_create_settlement_for_any_producer(self):
        """El administrador puede crear liquidaciones para cualquier productor."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            "/payroll/settlements/",
            {
                "worker": str(self.worker_prod2.id),
                "farm": str(self.farm2.id),
                "start_date": "2026-10-01",
                "end_date": "2026-10-31",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    # ------------------------------------------------------------------
    # AÑADIR JORNADAS POR JORNAL
    # ------------------------------------------------------------------

    def test_add_daily_workday_to_settlement_success(self):
        """Añade una jornada por jornal y conserva la tarifa aplicada."""
        settlement = self._create_settlement()
        workday = self._create_workday(date="2026-10-15", rate="50000.00")

        self.client.force_authenticate(user=self.prod1)
        response = self.client.post(
            "/payroll/settlements/add-workday/",
            {"settlement_id": str(settlement.id), "workday_id": str(workday.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Decimal(response.data["applied_daily_rate"]), Decimal("50000.00"))
        self.assertEqual(Decimal(response.data["paid_amount"]), Decimal("50000.00"))

    def test_add_duplicate_workday_rejected(self):
        """Una jornada no puede añadirse dos veces a la liquidación."""
        settlement = self._create_settlement()
        workday = self._create_workday(date="2026-10-15")

        self.client.force_authenticate(user=self.prod1)
        payload = {"settlement_id": str(settlement.id), "workday_id": str(workday.id)}
        first = self.client.post("/payroll/settlements/add-workday/", payload, format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        second = self.client.post("/payroll/settlements/add-workday/", payload, format="json")
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("ya", second.data["detail"].lower())

    def test_add_workday_from_other_worker_rejected(self):
        """La jornada debe pertenecer al trabajador de la liquidación."""
        settlement = self._create_settlement()
        other_workday = self._create_workday(worker=self.worker2, date="2026-10-15")

        self.client.force_authenticate(user=self.prod1)
        response = self.client.post(
            "/payroll/settlements/add-workday/",
            {"settlement_id": str(settlement.id), "workday_id": str(other_workday.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("trabajador", response.data["detail"])

    def test_add_workday_outside_period_rejected(self):
        """La jornada debe estar dentro del periodo de la liquidación."""
        settlement = self._create_settlement(
            start_date="2026-11-01", end_date="2026-11-30"
        )
        workday = self._create_workday(date="2026-10-15")

        self.client.force_authenticate(user=self.prod1)
        response = self.client.post(
            "/payroll/settlements/add-workday/",
            {"settlement_id": str(settlement.id), "workday_id": str(workday.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("período", response.data["detail"])

    def test_add_kilogram_workday_as_daily_rejected(self):
        """Las jornadas por kilogramo no se añaden al detalle por jornal."""
        settlement = self._create_settlement()
        kg_workday = self._create_workday(
            date="2026-10-15",
            payment_mode=Workday.PaymentMode.KILOGRAM,
            rate="1000.00",
        )

        self.client.force_authenticate(user=self.prod1)
        response = self.client.post(
            "/payroll/settlements/add-workday/",
            {"settlement_id": str(settlement.id), "workday_id": str(kg_workday.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("jornal", response.data["detail"])

    def test_add_workday_to_closed_settlement_rejected(self):
        """No se pueden añadir jornadas a una liquidación ya cerrada."""
        settlement = self._create_settlement(status_value=Settlement.Status.CLOSED)
        workday = self._create_workday(date="2026-10-15")

        self.client.force_authenticate(user=self.prod1)
        response = self.client.post(
            "/payroll/settlements/add-workday/",
            {"settlement_id": str(settlement.id), "workday_id": str(workday.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("abiertas", response.data["detail"])

    def test_add_workday_from_other_farm_rejected(self):
        """La jornada debe pertenecer a la finca de la liquidación."""
        settlement = self._create_settlement(farm=self.farm1)
        other_farm_workday = self._create_workday(date="2026-10-15", lot=self.lot1_alt)

        self.client.force_authenticate(user=self.prod1)
        response = self.client.post(
            "/payroll/settlements/add-workday/",
            {
                "settlement_id": str(settlement.id),
                "workday_id": str(other_farm_workday.id),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("finca", response.data["detail"])

    def test_add_workday_nonexistent_settlement_returns_404(self):
        """Un identificador de liquidación inexistente responde 404."""
        workday = self._create_workday(date="2026-10-15")
        self.client.force_authenticate(user=self.prod1)
        response = self.client.post(
            "/payroll/settlements/add-workday/",
            {
                "settlement_id": "00000000-0000-0000-0000-000000000000",
                "workday_id": str(workday.id),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_add_nonexistent_workday_rejected(self):
        """Un identificador de jornada inexistente responde 400."""
        settlement = self._create_settlement()
        self.client.force_authenticate(user=self.prod1)
        response = self.client.post(
            "/payroll/settlements/add-workday/",
            {
                "settlement_id": str(settlement.id),
                "workday_id": "00000000-0000-0000-0000-000000000000",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("no encontrada", response.data["detail"])

    def test_other_producer_cannot_add_workday_to_settlement(self):
        """Un productor no puede operar sobre la liquidación de otro (404)."""
        settlement = self._create_settlement()
        workday = self._create_workday(date="2026-10-15")

        self.client.force_authenticate(user=self.prod2)
        response = self.client.post(
            "/payroll/settlements/add-workday/",
            {"settlement_id": str(settlement.id), "workday_id": str(workday.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ------------------------------------------------------------------
    # AÑADIR PESAJES POR KILOGRAMO
    # ------------------------------------------------------------------

    def test_add_harvest_to_settlement_success(self):
        """Añade un pesaje por kg y calcula el importe con la tarifa acordada."""
        settlement = self._create_settlement()
        kg_workday = self._create_workday(
            date="2026-10-15",
            payment_mode=Workday.PaymentMode.KILOGRAM,
            rate="1000.00",
        )
        harvest = self._create_harvest(kg_workday, kg="25.500")

        self.client.force_authenticate(user=self.prod1)
        response = self.client.post(
            "/payroll/settlements/add-harvest/",
            {"settlement_id": str(settlement.id), "harvest_record_id": str(harvest.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Decimal(response.data["paid_kg"]), Decimal("25.500"))
        self.assertEqual(Decimal(response.data["applied_kg_rate"]), Decimal("1000.00"))
        self.assertEqual(Decimal(response.data["paid_amount"]), Decimal("25500.00"))

    def test_add_duplicate_harvest_rejected(self):
        """Un pesaje no puede añadirse dos veces a la liquidación."""
        settlement = self._create_settlement()
        kg_workday = self._create_workday(
            date="2026-10-15",
            payment_mode=Workday.PaymentMode.KILOGRAM,
            rate="1000.00",
        )
        harvest = self._create_harvest(kg_workday)

        self.client.force_authenticate(user=self.prod1)
        payload = {"settlement_id": str(settlement.id), "harvest_record_id": str(harvest.id)}
        first = self.client.post("/payroll/settlements/add-harvest/", payload, format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        second = self.client.post("/payroll/settlements/add-harvest/", payload, format="json")
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("ya", second.data["detail"].lower())

    def test_add_harvest_from_daily_workday_rejected(self):
        """Los pesajes solo se liquidan si la jornada es de modalidad kg."""
        settlement = self._create_settlement()
        daily_workday = self._create_workday(
            date="2026-10-15",
            payment_mode=Workday.PaymentMode.DAILY,
            activity=self.act_recoleccion,
        )
        harvest = self._create_harvest(daily_workday)

        self.client.force_authenticate(user=self.prod1)
        response = self.client.post(
            "/payroll/settlements/add-harvest/",
            {"settlement_id": str(settlement.id), "harvest_record_id": str(harvest.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("modalidad kg", response.data["detail"])

    def test_add_harvest_from_other_worker_rejected(self):
        """El pesaje debe pertenecer al trabajador de la liquidación."""
        settlement = self._create_settlement()
        other_worker_workday = self._create_workday(
            worker=self.worker2,
            date="2026-10-15",
            payment_mode=Workday.PaymentMode.KILOGRAM,
            rate="1000.00",
        )
        harvest = self._create_harvest(other_worker_workday)

        self.client.force_authenticate(user=self.prod1)
        response = self.client.post(
            "/payroll/settlements/add-harvest/",
            {"settlement_id": str(settlement.id), "harvest_record_id": str(harvest.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("trabajador", response.data["detail"])

    def test_add_harvest_outside_period_rejected(self):
        """El pesaje debe estar dentro del periodo de la liquidación."""
        settlement = self._create_settlement(
            start_date="2026-11-01", end_date="2026-11-30"
        )
        kg_workday = self._create_workday(
            date="2026-10-15",
            payment_mode=Workday.PaymentMode.KILOGRAM,
            rate="1000.00",
        )
        harvest = self._create_harvest(kg_workday)

        self.client.force_authenticate(user=self.prod1)
        response = self.client.post(
            "/payroll/settlements/add-harvest/",
            {"settlement_id": str(settlement.id), "harvest_record_id": str(harvest.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("período", response.data["detail"])

    def test_add_harvest_from_other_farm_rejected(self):
        """El pesaje debe pertenecer a la finca de la liquidación."""
        settlement = self._create_settlement(farm=self.farm1)
        kg_workday = self._create_workday(
            date="2026-10-15",
            payment_mode=Workday.PaymentMode.KILOGRAM,
            rate="1000.00",
            lot=self.lot1_alt,
        )
        harvest = self._create_harvest(kg_workday)

        self.client.force_authenticate(user=self.prod1)
        response = self.client.post(
            "/payroll/settlements/add-harvest/",
            {"settlement_id": str(settlement.id), "harvest_record_id": str(harvest.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("finca", response.data["detail"])

    def test_add_nonexistent_harvest_rejected(self):
        """Un identificador de pesaje inexistente responde 400."""
        settlement = self._create_settlement()
        self.client.force_authenticate(user=self.prod1)
        response = self.client.post(
            "/payroll/settlements/add-harvest/",
            {
                "settlement_id": str(settlement.id),
                "harvest_record_id": "00000000-0000-0000-0000-000000000000",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("no encontrado", response.data["detail"])

    def test_other_producer_cannot_add_harvest_to_settlement(self):
        """Un productor no puede añadir pesajes a la liquidación de otro (404)."""
        settlement = self._create_settlement()
        kg_workday = self._create_workday(
            date="2026-10-15",
            payment_mode=Workday.PaymentMode.KILOGRAM,
            rate="1000.00",
        )
        harvest = self._create_harvest(kg_workday)

        self.client.force_authenticate(user=self.prod2)
        response = self.client.post(
            "/payroll/settlements/add-harvest/",
            {"settlement_id": str(settlement.id), "harvest_record_id": str(harvest.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ------------------------------------------------------------------
    # CIERRE DE LIQUIDACIONES
    # ------------------------------------------------------------------

    def test_close_settlement_calculates_total_and_marks_workdays(self):
        """Cierra la liquidación, suma los importes y marca las jornadas como liquidadas."""
        settlement = self._create_settlement()
        workday1 = self._create_workday(date="2026-10-15", rate="50000.00")
        workday2 = self._create_workday(date="2026-10-16", rate="50000.00")

        self.client.force_authenticate(user=self.prod1)
        for workday in (workday1, workday2):
            response = self.client.post(
                "/payroll/settlements/add-workday/",
                {"settlement_id": str(settlement.id), "workday_id": str(workday.id)},
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.client.post(
            "/payroll/settlements/close/",
            {"settlement_id": str(settlement.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], Settlement.Status.CLOSED)
        self.assertEqual(Decimal(response.data["total_calculated"]), Decimal("100000.00"))
        self.assertIsNotNone(response.data["closed_at"])

        workday1.refresh_from_db()
        workday2.refresh_from_db()
        self.assertEqual(workday1.settlement_status, Workday.SettlementStatus.SETTLED)
        self.assertEqual(workday2.settlement_status, Workday.SettlementStatus.SETTLED)

    def test_close_harvest_settlement_calculates_total_and_marks_records(self):
        """Cierra una liquidación por kg y marca los pesajes como liquidados."""
        settlement = self._create_settlement()
        kg_workday = self._create_workday(
            date="2026-10-15",
            payment_mode=Workday.PaymentMode.KILOGRAM,
            rate="1000.00",
        )
        harvest = self._create_harvest(kg_workday, kg="25.500")

        self.client.force_authenticate(user=self.prod1)
        self.client.post(
            "/payroll/settlements/add-harvest/",
            {"settlement_id": str(settlement.id), "harvest_record_id": str(harvest.id)},
            format="json",
        )
        response = self.client.post(
            "/payroll/settlements/close/",
            {"settlement_id": str(settlement.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(response.data["total_calculated"]), Decimal("25500.00"))

        harvest.refresh_from_db()
        kg_workday.refresh_from_db()
        self.assertEqual(
            harvest.settlement_status, HarvestRecord.SettlementStatus.SETTLED
        )
        self.assertEqual(kg_workday.settlement_status, Workday.SettlementStatus.SETTLED)

    def test_close_empty_settlement_total_zero(self):
        """Cerrar una liquidación sin detalles genera total cero."""
        settlement = self._create_settlement()
        self.client.force_authenticate(user=self.prod1)
        response = self.client.post(
            "/payroll/settlements/close/",
            {"settlement_id": str(settlement.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(response.data["total_calculated"]), Decimal("0.00"))

    def test_close_already_closed_settlement_rejected(self):
        """No se puede cerrar dos veces la misma liquidación."""
        settlement = self._create_settlement(status_value=Settlement.Status.CLOSED)
        self.client.force_authenticate(user=self.prod1)
        response = self.client.post(
            "/payroll/settlements/close/",
            {"settlement_id": str(settlement.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("abiertas", response.data["detail"])

    def test_close_nonexistent_settlement_returns_404(self):
        """Un identificador de liquidación inexistente responde 404."""
        self.client.force_authenticate(user=self.prod1)
        response = self.client.post(
            "/payroll/settlements/close/",
            {"settlement_id": "00000000-0000-0000-0000-000000000000"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_other_producer_cannot_close_settlement(self):
        """Un productor no puede cerrar la liquidación de otro productor."""
        settlement = self._create_settlement()
        self.client.force_authenticate(user=self.prod2)
        response = self.client.post(
            "/payroll/settlements/close/",
            {"settlement_id": str(settlement.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        settlement.refresh_from_db()
        self.assertEqual(settlement.status, Settlement.Status.OPEN)

    def test_settled_workday_cannot_be_added_to_another_settlement(self):
        """
        Regla 3 (SRS módulo 7): un registro de trabajo no puede incluirse en
        más de una liquidación, ni siquiera tras cerrar la primera.
        """
        first_settlement = self._create_settlement()
        workday = self._create_workday(date="2026-10-15")

        self.client.force_authenticate(user=self.prod1)
        self.client.post(
            "/payroll/settlements/add-workday/",
            {"settlement_id": str(first_settlement.id), "workday_id": str(workday.id)},
            format="json",
        )
        self.client.post(
            "/payroll/settlements/close/",
            {"settlement_id": str(first_settlement.id)},
            format="json",
        )

        second_settlement = self._create_settlement(
            start_date="2026-10-01", end_date="2026-10-31"
        )
        response = self.client.post(
            "/payroll/settlements/add-workday/",
            {"settlement_id": str(second_settlement.id), "workday_id": str(workday.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("liquidada", response.data["detail"])

    def test_settled_harvest_cannot_be_added_to_another_settlement(self):
        """
        Regla 3 (SRS módulo 7): un pesaje ya liquidado no puede incluirse en
        otra liquidación.
        """
        first_settlement = self._create_settlement()
        kg_workday = self._create_workday(
            date="2026-10-15",
            payment_mode=Workday.PaymentMode.KILOGRAM,
            rate="1000.00",
        )
        harvest = self._create_harvest(kg_workday, kg="10.000")

        self.client.force_authenticate(user=self.prod1)
        self.client.post(
            "/payroll/settlements/add-harvest/",
            {"settlement_id": str(first_settlement.id), "harvest_record_id": str(harvest.id)},
            format="json",
        )
        self.client.post(
            "/payroll/settlements/close/",
            {"settlement_id": str(first_settlement.id)},
            format="json",
        )

        second_settlement = self._create_settlement(
            start_date="2026-10-01", end_date="2026-10-31"
        )
        response = self.client.post(
            "/payroll/settlements/add-harvest/",
            {"settlement_id": str(second_settlement.id), "harvest_record_id": str(harvest.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("liquidado", response.data["detail"])

    def test_closed_settlement_keeps_applied_rates_after_rate_change(self):
        """
        Regla 6 (SRS módulo 6) / regla 8 (módulo 7): cambiar la tarifa de una
        jornada no altera los valores de una liquidación ya cerrada.
        """
        settlement = self._create_settlement()
        workday = self._create_workday(date="2026-10-15", rate="50000.00")

        self.client.force_authenticate(user=self.prod1)
        self.client.post(
            "/payroll/settlements/add-workday/",
            {"settlement_id": str(settlement.id), "workday_id": str(workday.id)},
            format="json",
        )
        self.client.post(
            "/payroll/settlements/close/",
            {"settlement_id": str(settlement.id)},
            format="json",
        )

        # Cambio posterior de la tarifa en la jornada original
        workday.agreed_rate = Decimal("90000.00")
        workday.save(update_fields=["agreed_rate"])

        settlement.refresh_from_db()
        detail = SettlementDetailWorkday.objects.get(settlement=settlement)
        self.assertEqual(settlement.total_calculated, Decimal("50000.00"))
        self.assertEqual(detail.applied_daily_rate, Decimal("50000.00"))
        self.assertEqual(detail.paid_amount, Decimal("50000.00"))

    # ------------------------------------------------------------------
    # PAGOS LABORALES
    # ------------------------------------------------------------------

    def test_pay_closed_settlement_success(self):
        """Registra el pago exacto del total de una liquidación cerrada."""
        settlement = self._create_settlement(status_value=Settlement.Status.CLOSED)
        settlement.total_calculated = Decimal("50000.00")
        settlement.save(update_fields=["total_calculated"])

        self.client.force_authenticate(user=self.prod1)
        response = self.client.post(
            "/payroll/settlements/pay/",
            {
                "settlement_id": str(settlement.id),
                "date": "2026-11-01",
                "amount_paid": "50000.00",
                "payment_method": "efectivo",
                "notes": "Pago en efectivo",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Decimal(response.data["amount_paid"]), Decimal("50000.00"))

        settlement.refresh_from_db()
        self.assertEqual(settlement.status, Settlement.Status.PAID)
        self.assertIsNotNone(settlement.paid_at)
        self.assertTrue(LaborPayment.objects.filter(settlement=settlement).exists())

    def test_pay_partial_amount_rejected(self):
        """No se permiten pagos parciales (monto distinto al total)."""
        settlement = self._create_settlement(status_value=Settlement.Status.CLOSED)
        settlement.total_calculated = Decimal("50000.00")
        settlement.save(update_fields=["total_calculated"])

        self.client.force_authenticate(user=self.prod1)
        response = self.client.post(
            "/payroll/settlements/pay/",
            {
                "settlement_id": str(settlement.id),
                "date": "2026-11-01",
                "amount_paid": "25000.00",
                "payment_method": "efectivo",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("total calculado", response.data["detail"])
        self.assertFalse(LaborPayment.objects.filter(settlement=settlement).exists())

    def test_pay_open_settlement_rejected(self):
        """No se puede pagar una liquidación que aún está abierta."""
        settlement = self._create_settlement()
        self.client.force_authenticate(user=self.prod1)
        response = self.client.post(
            "/payroll/settlements/pay/",
            {
                "settlement_id": str(settlement.id),
                "date": "2026-11-01",
                "amount_paid": "0.00",
                "payment_method": "efectivo",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("cerrada", response.data["detail"])

    def test_pay_already_paid_settlement_rejected(self):
        """No se puede registrar dos veces el pago de la misma liquidación."""
        settlement, _ = self._create_closed_settlement_with_payment()

        self.client.force_authenticate(user=self.prod1)
        response = self.client.post(
            "/payroll/settlements/pay/",
            {
                "settlement_id": str(settlement.id),
                "date": "2026-11-02",
                "amount_paid": "50000.00",
                "payment_method": "efectivo",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            LaborPayment.objects.filter(settlement=settlement).count(), 1
        )

    def test_pay_nonexistent_settlement_returns_404(self):
        """Un identificador de liquidación inexistente responde 404."""
        self.client.force_authenticate(user=self.prod1)
        response = self.client.post(
            "/payroll/settlements/pay/",
            {
                "settlement_id": "00000000-0000-0000-0000-000000000000",
                "date": "2026-11-01",
                "amount_paid": "1000.00",
                "payment_method": "efectivo",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_other_producer_cannot_pay_settlement(self):
        """Un productor no puede pagar la liquidación de otro productor."""
        settlement = self._create_settlement(status_value=Settlement.Status.CLOSED)
        settlement.total_calculated = Decimal("50000.00")
        settlement.save(update_fields=["total_calculated"])

        self.client.force_authenticate(user=self.prod2)
        response = self.client.post(
            "/payroll/settlements/pay/",
            {
                "settlement_id": str(settlement.id),
                "date": "2026-11-01",
                "amount_paid": "50000.00",
                "payment_method": "efectivo",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(LaborPayment.objects.filter(settlement=settlement).exists())

    # ------------------------------------------------------------------
    # AISLAMIENTO Y PERMISOS
    # ------------------------------------------------------------------

    def test_settlement_list_only_shows_own_records(self):
        """Cada productor ve sus liquidaciones; el administrador ve todas."""
        own = self._create_settlement(worker=self.worker1, farm=self.farm1)
        foreign = self._create_settlement(
            worker=self.worker_prod2,
            farm=self.farm2,
            start_date="2026-11-01",
            end_date="2026-11-30",
        )

        self.client.force_authenticate(user=self.prod1)
        response = self.client.get("/payroll/settlements/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [item["id"] for item in response.data]
        self.assertIn(str(own.id), ids)
        self.assertNotIn(str(foreign.id), ids)

        self.client.force_authenticate(user=self.admin)
        admin_response = self.client.get("/payroll/settlements/")
        admin_ids = [item["id"] for item in admin_response.data]
        self.assertIn(str(own.id), admin_ids)
        self.assertIn(str(foreign.id), admin_ids)

    def test_other_producer_cannot_retrieve_settlement(self):
        """Un productor no puede consultar la liquidación de otro (404)."""
        settlement = self._create_settlement()
        self.client.force_authenticate(user=self.prod2)
        response = self.client.get(f"/payroll/settlements/{settlement.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_settlement_list_rejected(self):
        """Sin autenticación no se puede listar liquidaciones."""
        response = self.client.get("/payroll/settlements/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_settlement_detail_and_payment_endpoints_are_read_only(self):
        """
        Los detalles y pagos no permiten escritura directa: toda mutación pasa
        por los servicios, preservando la integridad de tarifas e importes.
        """
        self.client.force_authenticate(user=self.prod1)
        for url in (
            "/payroll/settlement-workdays/",
            "/payroll/settlement-harvests/",
            "/payroll/payments/",
        ):
            response = self.client.post(url, {}, format="json")
            self.assertEqual(
                response.status_code,
                status.HTTP_405_METHOD_NOT_ALLOWED,
                msg=f"{url} debería ser de solo lectura",
            )

    def test_owner_can_retrieve_settlement_details_and_payment(self):
        """El dueño puede consultar sus detalles de liquidación y pagos."""
        settlement, payment = self._create_closed_settlement_with_payment()
        workday_detail = SettlementDetailWorkday.objects.get(settlement=settlement)

        self.client.force_authenticate(user=self.prod1)
        detail_response = self.client.get(
            f"/payroll/settlement-workdays/{workday_detail.id}/"
        )
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)

        payment_response = self.client.get(f"/payroll/payments/{payment.id}/")
        self.assertEqual(payment_response.status_code, status.HTTP_200_OK)

    def test_other_producer_cannot_retrieve_settlement_details(self):
        """Otro productor no puede consultar detalles de liquidación ajenos."""
        settlement = self._create_settlement()
        workday = self._create_workday(date="2026-10-15")
        workday_detail = SettlementDetailWorkday.objects.create(
            settlement=settlement,
            workday=workday,
            applied_daily_rate=Decimal("50000.00"),
            paid_amount=Decimal("50000.00"),
        )

        self.client.force_authenticate(user=self.prod2)
        response = self.client.get(
            f"/payroll/settlement-workdays/{workday_detail.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ------------------------------------------------------------------
    # INMUTABILIDAD DE LIQUIDACIONES CERRADAS/PAGADAS
    # ------------------------------------------------------------------

    def test_open_settlement_with_details_cannot_change_scope(self):
        """
        Con detalles asociados no se puede cambiar trabajador, finca ni periodo:
        los registros incluidos ya pertenecen a ese alcance.
        """
        settlement = self._create_settlement()
        workday = self._create_workday(date="2026-10-15")
        SettlementDetailWorkday.objects.create(
            settlement=settlement,
            workday=workday,
            applied_daily_rate=Decimal("50000.00"),
            paid_amount=Decimal("50000.00"),
        )

        self.client.force_authenticate(user=self.prod1)
        response = self.client.patch(
            f"/payroll/settlements/{settlement.id}/",
            {"worker": str(self.worker2.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("worker", response.data)

        settlement.refresh_from_db()
        self.assertEqual(settlement.worker, self.worker1)

    def test_closed_settlement_cannot_be_modified(self):
        """Una liquidación cerrada no puede modificarse por cambio de tarifas."""
        settlement = self._create_settlement(status_value=Settlement.Status.CLOSED)
        self.client.force_authenticate(user=self.prod1)
        response = self.client.patch(
            f"/payroll/settlements/{settlement.id}/",
            {"end_date": "2026-12-31"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("cerrada o pagada", response.data["detail"])

    def test_paid_settlement_cannot_be_deleted(self):
        """Una liquidación pagada conserva su historial y no puede eliminarse."""
        settlement, _ = self._create_closed_settlement_with_payment()
        self.client.force_authenticate(user=self.prod1)
        response = self.client.delete(f"/payroll/settlements/{settlement.id}/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("historial", response.data["detail"])
        self.assertTrue(Settlement.objects.filter(id=settlement.id).exists())

    def test_open_settlement_without_details_can_be_deleted(self):
        """Una liquidación abierta sin detalles puede eliminarse."""
        settlement = self._create_settlement()
        self.client.force_authenticate(user=self.prod1)
        response = self.client.delete(f"/payroll/settlements/{settlement.id}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Settlement.objects.filter(id=settlement.id).exists())

    def test_open_settlement_with_details_cannot_be_deleted(self):
        """Una liquidación abierta con detalles no puede eliminarse (historial protegido)."""
        settlement = self._create_settlement()
        workday = self._create_workday(date="2026-10-15")
        SettlementDetailWorkday.objects.create(
            settlement=settlement,
            workday=workday,
            applied_daily_rate=Decimal("50000.00"),
            paid_amount=Decimal("50000.00"),
        )

        self.client.force_authenticate(user=self.prod1)
        response = self.client.delete(f"/payroll/settlements/{settlement.id}/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(Settlement.objects.filter(id=settlement.id).exists())
