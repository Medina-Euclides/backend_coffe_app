from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import UserRole
from apps.farms.models import Farm
from apps.finance.models import OperatingExpense
from apps.labor.models import Worker
from apps.payroll.models import LaborPayment, Settlement

User = get_user_model()


class FinanceAPITests(APITestCase):
    def setUp(self):
        self.producer = User.objects.create_user(
            email="producer@finance.test",
            password="test-password",
            first_name="Ana",
            last_name="Café",
            role=UserRole.PRODUCER,
        )
        self.other_producer = User.objects.create_user(
            email="other@finance.test",
            password="test-password",
            first_name="Luis",
            last_name="Pérez",
            role=UserRole.PRODUCER,
        )
        self.farm = Farm.objects.create(id_productor=self.producer, name="El Porvenir")
        self.other_farm = Farm.objects.create(
            id_productor=self.other_producer, name="Finca ajena"
        )

    def test_create_manual_operating_expense(self):
        self.client.force_authenticate(user=self.producer)

        response = self.client.post(
            "/finance/expenses/",
            {
                "farm": str(self.farm.id),
                "date": "2026-10-22",
                "concept": "Compra de fertilizante",
                "amount": "150000.00",
                "category": OperatingExpense.Category.INPUTS,
                "notes": "Aplicación para el lote 1",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["farm_name"], self.farm.name)
        self.assertEqual(response.data["category"], OperatingExpense.Category.INPUTS)
        self.assertEqual(Decimal(response.data["amount"]), Decimal("150000.00"))

    def test_manual_labor_expense_is_rejected(self):
        self.client.force_authenticate(user=self.producer)

        response = self.client.post(
            "/finance/expenses/",
            {
                "farm": str(self.farm.id),
                "date": "2026-10-22",
                "concept": "Pago de jornales",
                "amount": "50000.00",
                "category": OperatingExpense.Category.LABOR,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("category", response.data)
        self.assertFalse(OperatingExpense.objects.exists())

    def test_expense_list_is_scoped_and_can_be_filtered(self):
        OperatingExpense.objects.create(
            farm=self.farm,
            date="2026-10-20",
            concept="Compra de abono",
            amount=Decimal("10000.00"),
            category=OperatingExpense.Category.INPUTS,
        )
        OperatingExpense.objects.create(
            farm=self.farm,
            date="2026-10-25",
            concept="Transporte",
            amount=Decimal("20000.00"),
            category=OperatingExpense.Category.TRANSPORT,
        )
        OperatingExpense.objects.create(
            farm=self.other_farm,
            date="2026-10-22",
            concept="Gasto de otra finca",
            amount=Decimal("30000.00"),
            category=OperatingExpense.Category.INPUTS,
        )
        self.client.force_authenticate(user=self.producer)

        response = self.client.get(
            "/finance/expenses/?category=inputs&date_from=2026-10-19&date_to=2026-10-21"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["concept"], "Compra de abono")

    def test_invalid_expense_filter_returns_bad_request(self):
        self.client.force_authenticate(user=self.producer)

        response = self.client.get("/finance/expenses/?date_from=no-es-fecha")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("date_from", response.data)

    def test_producer_cannot_create_expense_for_another_farm(self):
        self.client.force_authenticate(user=self.producer)

        response = self.client.post(
            "/finance/expenses/",
            {
                "farm": str(self.other_farm.id),
                "date": "2026-10-22",
                "concept": "Compra ajena",
                "amount": "10000.00",
                "category": OperatingExpense.Category.INPUTS,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(OperatingExpense.objects.exists())

    def test_labor_payment_automatically_creates_linked_expense_once(self):
        worker = Worker.objects.create(
            producer=self.producer,
            first_name="Juan",
            last_name="Gómez",
        )
        settlement = Settlement.objects.create(
            worker=worker,
            farm=self.farm,
            start_date="2026-10-01",
            end_date="2026-10-31",
            total_calculated=Decimal("50000.00"),
            status=Settlement.Status.CLOSED,
        )

        payment = LaborPayment.objects.create(
            settlement=settlement,
            date="2026-10-22",
            amount_paid=Decimal("50000.00"),
            payment_method=LaborPayment.PaymentMethod.CASH,
            notes="Pago en efectivo",
        )
        payment.refresh_from_db()

        expense = OperatingExpense.objects.get(labor_payment=payment)
        self.assertEqual(expense.farm, self.farm)
        self.assertEqual(expense.date, payment.date)
        self.assertEqual(expense.amount, payment.amount_paid)
        self.assertEqual(expense.category, OperatingExpense.Category.LABOR)
        self.assertIn("Juan Gómez", expense.concept)
        self.assertEqual(expense.notes, payment.notes)

        payment.notes = "Pago registrado"
        payment.save(update_fields=["notes"])
        self.assertEqual(
            OperatingExpense.objects.filter(labor_payment=payment).count(),
            1,
        )

    def test_payment_generated_expense_cannot_be_changed_or_deleted(self):
        worker = Worker.objects.create(
            producer=self.producer,
            first_name="Juan",
            last_name="Gómez",
        )
        settlement = Settlement.objects.create(
            worker=worker,
            farm=self.farm,
            start_date="2026-10-01",
            end_date="2026-10-31",
            total_calculated=Decimal("50000.00"),
            status=Settlement.Status.CLOSED,
        )
        payment = LaborPayment.objects.create(
            settlement=settlement,
            date="2026-10-22",
            amount_paid=Decimal("50000.00"),
            payment_method=LaborPayment.PaymentMethod.CASH,
        )
        expense = OperatingExpense.objects.get(labor_payment=payment)
        self.client.force_authenticate(user=self.producer)

        update_response = self.client.patch(
            f"/finance/expenses/{expense.id}/",
            {"concept": "Concepto alterado"},
            format="json",
        )
        delete_response = self.client.delete(f"/finance/expenses/{expense.id}/")

        self.assertEqual(update_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(delete_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        expense.refresh_from_db()
        self.assertIn("Juan Gómez", expense.concept)

    def test_finance_endpoints_require_authentication(self):
        response = self.client.get("/finance/expenses/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
