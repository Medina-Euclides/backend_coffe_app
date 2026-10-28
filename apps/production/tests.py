from datetime import date, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.farms.models import Farm, Lot
from apps.labor.models import (
    ActivityType,
    HarvestRecord,
    Workday,
    WorkdayDetail,
    Worker,
)
from apps.production.models import Sale

User = get_user_model()


class ProductionModuleTests(TestCase):
    """Base de pruebas del módulo production con datos de dos productores."""

    def setUp(self):
        """Crea usuarios, fincas, lotes, trabajador y una jornada con recolección."""
        self.client = APIClient()

        # Usuario administrador (ve todas las fincas).
        self.admin = User.objects.create_user(
            email='admin_test@cafe.com',
            password='pass123',
            first_name='Admin',
            last_name='Test',
            role='ADMIN'
        )
        self.admin.is_staff = True
        self.admin.is_superuser = True
        self.admin.save()

        # Dos productores independientes para probar el aislamiento.
        self.producer1 = User.objects.create_user(
            email='prod1@cafe.com',
            password='pass123',
            first_name='Juan',
            last_name='Productor',
            role='PRODUCER'
        )
        self.producer2 = User.objects.create_user(
            email='prod2@cafe.com',
            password='pass123',
            first_name='Pedro',
            last_name='Productor',
            role='PRODUCER'
        )

        # Una finca por productor.
        self.farm1 = Farm.objects.create(
            id_productor=self.producer1,
            name='Finca El Porvenir',
            location='Zona 1',
        )
        self.farm2 = Farm.objects.create(
            id_productor=self.producer2,
            name='Finca La Esperanza',
            location='Zona 2',
        )

        # Un lote por finca.
        self.lot1_f1 = Lot.objects.create(
            id_farm=self.farm1,
            name='Lote 1',
            area_m2=2000,
            is_active=True
        )
        self.lot2_f2 = Lot.objects.create(
            id_farm=self.farm2,
            name='Lote 2',
            area_m2=1500,
            is_active=True
        )

        # Trabajador, actividad, jornada y recolección del productor 1.
        self.worker1 = Worker.objects.create(
            producer=self.producer1,
            identification='10001',
            first_name='Juan',
            last_name='Gómez',
            is_active=True
        )
        self.activity_recoleccion = ActivityType.objects.create(
            producer=self.producer1,
            name='Recolección',
            description='Recolección de café maduro',
            is_harvest=True
        )
        self.workday = Workday.objects.create(
            worker=self.worker1,
            date=date(2026, 10, 20),
            payment_mode='DAILY',
            agreed_rate=Decimal('50000.00'),
        )
        self.workday_detail = WorkdayDetail.objects.create(
            workday=self.workday,
            activity_type=self.activity_recoleccion,
            lot=self.lot1_f1
        )
        self.harvest = HarvestRecord.objects.create(
            workday_detail=self.workday_detail,
            quantity_kg=Decimal('25.50'),
            time=time(10, 0)
        )

        self.base_url_sales = '/production/sales/'
        self.base_url_prod = '/production/production/'


class SaleCRUDTests(ProductionModuleTests):
    """Pruebas CRUD de ventas y de las reglas de negocio del módulo."""

    def test_list_sales_unauthenticated_forbidden(self):
        """Sin autenticación debe rechazar el listado."""
        resp = self.client.get(self.base_url_sales)
        self.assertIn(resp.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_producer_lists_only_own_farm_sales(self):
        """El productor solo ve ventas de sus propias fincas."""
        Sale.objects.create(
            farm=self.farm2,
            sale_date=date(2026, 10, 1),
            coffee_type='pergamino',
            quantity_kg=Decimal('100.00'),
            unit_price=Decimal('8000.00'),
            total_amount=Decimal('800000.00'),
            buyer='Comprador X'
        )
        self.client.force_authenticate(user=self.producer1)
        resp = self.client.get(self.base_url_sales)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 0)

    def test_admin_lists_all_sales(self):
        """El administrador ve las ventas de todas las fincas."""
        Sale.objects.create(
            farm=self.farm1,
            sale_date=date(2026, 10, 1),
            coffee_type='pergamino',
            quantity_kg=Decimal('100.00'),
            unit_price=Decimal('8000.00'),
            total_amount=Decimal('800000.00'),
        )
        Sale.objects.create(
            farm=self.farm2,
            sale_date=date(2026, 10, 5),
            coffee_type='pasilla',
            quantity_kg=Decimal('50.00'),
            unit_price=Decimal('2000.00'),
            total_amount=Decimal('100000.00'),
        )
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get(self.base_url_sales)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 2)

    def test_create_sale_auto_calculates_total(self):
        """Al crear una venta, total_amount se calcula como cantidad por precio."""
        self.client.force_authenticate(user=self.producer1)
        data = {
            'farm': str(self.farm1.id),
            'sale_date': '2026-10-23',
            'coffee_type': 'pergamino',
            'quantity_kg': '100.00',
            'unit_price': '8000.00',
            'buyer': 'Comprador A'
        }
        resp = self.client.post(self.base_url_sales, data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Decimal(str(resp.data['total_amount'])), Decimal('800000.00'))
        sale = Sale.objects.get(id=resp.data['id'])
        self.assertEqual(sale.total_amount, Decimal('800000.00'))

    def test_create_sale_without_buyer(self):
        """La venta se puede registrar sin comprador (campo opcional)."""
        self.client.force_authenticate(user=self.producer1)
        data = {
            'farm': str(self.farm1.id),
            'sale_date': '2026-10-23',
            'coffee_type': 'pergamino',
            'quantity_kg': '100.00',
            'unit_price': '8000.00',
        }
        resp = self.client.post(self.base_url_sales, data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(resp.data['buyer'])

    def test_create_sale_future_date_rejected(self):
        """Rechaza una venta con fecha posterior a hoy."""
        self.client.force_authenticate(user=self.producer1)
        data = {
            'farm': str(self.farm1.id),
            'sale_date': '2099-01-01',
            'coffee_type': 'pergamino',
            'quantity_kg': '100.00',
            'unit_price': '8000.00',
        }
        resp = self.client.post(self.base_url_sales, data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('sale_date', resp.data)

    def test_producer_cannot_create_sale_for_other_farm(self):
        """El productor no puede registrar ventas en fincas ajenas."""
        self.client.force_authenticate(user=self.producer1)
        data = {
            'farm': str(self.farm2.id),
            'sale_date': '2026-10-23',
            'coffee_type': 'pergamino',
            'quantity_kg': '100.00',
            'unit_price': '8000.00',
        }
        resp = self.client.post(self.base_url_sales, data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_sale_quantity_must_be_positive(self):
        """La cantidad en kg debe ser mayor a cero."""
        self.client.force_authenticate(user=self.producer1)
        data = {
            'farm': str(self.farm1.id),
            'sale_date': '2026-10-23',
            'coffee_type': 'pergamino',
            'quantity_kg': '0',
            'unit_price': '8000.00',
        }
        resp = self.client.post(self.base_url_sales, data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_sale_unit_price_must_be_positive(self):
        """El precio unitario debe ser mayor a cero."""
        self.client.force_authenticate(user=self.producer1)
        data = {
            'farm': str(self.farm1.id),
            'sale_date': '2026-10-23',
            'coffee_type': 'pergamino',
            'quantity_kg': '100.00',
            'unit_price': '-100.00',
        }
        resp = self.client.post(self.base_url_sales, data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_sale_invalid_coffee_type(self):
        """Rechaza un tipo de café que no esté en el catálogo."""
        self.client.force_authenticate(user=self.producer1)
        data = {
            'farm': str(self.farm1.id),
            'sale_date': '2026-10-23',
            'coffee_type': 'verde',
            'quantity_kg': '100.00',
            'unit_price': '8000.00',
        }
        resp = self.client.post(self.base_url_sales, data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_retrieve_update_and_soft_delete_sale(self):
        """Recupera, actualiza y desactiva la venta sin borrarla físicamente."""
        sale = Sale.objects.create(
            farm=self.farm1,
            sale_date=date(2026, 10, 1),
            coffee_type='pergamino',
            quantity_kg=Decimal('100.00'),
            unit_price=Decimal('8000.00'),
            total_amount=Decimal('800000.00'),
        )
        self.client.force_authenticate(user=self.producer1)

        # Recuperar la venta.
        resp = self.client.get(f'{self.base_url_sales}{sale.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        # Actualizar el comprador.
        resp = self.client.patch(f'{self.base_url_sales}{sale.id}/', {'buyer': 'Nuevo Comprador'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        sale.refresh_from_db()
        self.assertEqual(sale.buyer, 'Nuevo Comprador')

        # El borrado es lógico: responde 204 pero la venta sigue existiendo inactiva.
        resp = self.client.delete(f'{self.base_url_sales}{sale.id}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        sale.refresh_from_db()
        self.assertFalse(sale.is_active)

        # Ya no aparece en el listado activo ni se puede recuperar por detalle.
        resp = self.client.get(self.base_url_sales)
        self.assertEqual(len(resp.data), 0)
        resp = self.client.get(f'{self.base_url_sales}{sale.id}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class RevenueSummaryTests(ProductionModuleTests):
    """Pruebas de consolidación de ingresos por ventas agrupados por finca."""

    def _create_sale(self, farm, amount, quantity='100.00', sale_date=date(2026, 10, 1)):
        """Crea una venta de apoyo con el total indicado."""
        return Sale.objects.create(
            farm=farm,
            sale_date=sale_date,
            coffee_type='pergamino',
            quantity_kg=Decimal(quantity),
            unit_price=Decimal('8000.00'),
            total_amount=Decimal(amount),
        )

    def test_revenue_by_farm_producer_sees_own_sales(self):
        """El productor solo consolida los ingresos de sus propias fincas."""
        self._create_sale(self.farm1, '800000.00')
        self._create_sale(self.farm2, '100000.00')
        self.client.force_authenticate(user=self.producer1)
        resp = self.client.get(f'{self.base_url_sales}revenue-by-farm/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(str(resp.data[0]['farm_id']), str(self.farm1.id))
        self.assertEqual(Decimal(str(resp.data[0]['total_revenue'])), Decimal('800000.00'))
        self.assertEqual(resp.data[0]['total_sales'], 1)

    def test_revenue_by_farm_producer_cannot_see_other_farm(self):
        """El productor no puede consultar ingresos de una finca ajena."""
        self.client.force_authenticate(user=self.producer1)
        resp = self.client.get(f'{self.base_url_sales}revenue-by-farm/?farm_id={self.farm2.id}')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_revenue_by_farm_admin_sees_all(self):
        """El administrador consolida los ingresos de todas las fincas."""
        self._create_sale(self.farm1, '800000.00')
        self._create_sale(self.farm2, '100000.00')
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get(f'{self.base_url_sales}revenue-by-farm/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 2)

    def test_revenue_by_farm_filter_by_year_and_month(self):
        """Filtra los ingresos por año y mes de la venta."""
        self._create_sale(self.farm1, '800000.00')
        self.client.force_authenticate(user=self.producer1)

        resp = self.client.get(f'{self.base_url_sales}revenue-by-farm/?year=2026&month=10')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)

        resp = self.client.get(f'{self.base_url_sales}revenue-by-farm/?year=2026&month=1')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 0)

    def test_revenue_by_farm_excludes_inactive_sales(self):
        """Las ventas desactivadas no deben sumar en los ingresos."""
        sale = self._create_sale(self.farm1, '800000.00')
        sale.is_active = False
        sale.save(update_fields=['is_active'])
        self.client.force_authenticate(user=self.producer1)
        resp = self.client.get(f'{self.base_url_sales}revenue-by-farm/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 0)

    def test_revenue_by_farm_invalid_month(self):
        """Rechaza un mes fuera del rango 1-12."""
        self.client.force_authenticate(user=self.producer1)
        resp = self.client.get(f'{self.base_url_sales}revenue-by-farm/?month=13')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class ProductionConsolidationTests(ProductionModuleTests):
    """Pruebas de consolidación de producción desde HarvestRecord."""

    def test_by_farm_producer_sees_own_production(self):
        """El productor ve la producción consolidada de su finca."""
        self.client.force_authenticate(user=self.producer1)
        resp = self.client.get(f'{self.base_url_prod}by-farm/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(len(resp.data) >= 1)
        farm_data = next((item for item in resp.data if str(item['farm_id']) == str(self.farm1.id)), None)
        self.assertIsNotNone(farm_data)
        self.assertEqual(farm_data['farm_name'], 'Finca El Porvenir')
        self.assertEqual(Decimal(str(farm_data['total_quantity_kg'])), Decimal('25.50'))
        self.assertEqual(farm_data['total_harvest_records'], 1)

    def test_by_farm_producer_cannot_see_other_farm(self):
        """El productor no ve producción de una finca ajena."""
        self.client.force_authenticate(user=self.producer1)
        resp = self.client.get(f'{self.base_url_prod}by-farm/?farm_id={self.farm2.id}')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_by_farm_filter_by_year(self):
        """Filtra la producción por año de la jornada."""
        self.client.force_authenticate(user=self.producer1)
        resp = self.client.get(f'{self.base_url_prod}by-farm/?year=2026')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(len(resp.data) >= 1)
        resp2 = self.client.get(f'{self.base_url_prod}by-farm/?year=2020')
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp2.data), 0)

    def test_by_farm_filter_by_month(self):
        """Filtra la producción por mes de la jornada."""
        self.client.force_authenticate(user=self.producer1)
        resp = self.client.get(f'{self.base_url_prod}by-farm/?year=2026&month=10')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(len(resp.data) >= 1)
        resp2 = self.client.get(f'{self.base_url_prod}by-farm/?year=2026&month=1')
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp2.data), 0)

    def test_by_lot_producer_sees_own_production(self):
        """El productor ve la producción consolidada por lote."""
        self.client.force_authenticate(user=self.producer1)
        resp = self.client.get(f'{self.base_url_prod}by-lot/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(len(resp.data) >= 1)
        lot_data = next((item for item in resp.data if str(item['lot_id']) == str(self.lot1_f1.id)), None)
        self.assertIsNotNone(lot_data)
        self.assertEqual(lot_data['lot_name'], 'Lote 1')
        self.assertEqual(lot_data['farm_name'], 'Finca El Porvenir')
        self.assertEqual(Decimal(str(lot_data['total_quantity_kg'])), Decimal('25.50'))
        self.assertEqual(lot_data['total_harvest_records'], 1)

    def test_by_lot_filter_by_lot_id(self):
        """Filtra la producción por un lote específico."""
        self.client.force_authenticate(user=self.producer1)
        resp = self.client.get(f'{self.base_url_prod}by-lot/?lot_id={self.lot1_f1.id}')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(len(resp.data) >= 1)

    def test_by_lot_producer_cannot_see_other_lot(self):
        """El productor no puede ver un lote ajeno."""
        self.client.force_authenticate(user=self.producer1)
        resp = self.client.get(f'{self.base_url_prod}by-lot/?lot_id={self.lot2_f2.id}')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_by_farm_without_filters_sees_all(self):
        """El administrador sin filtros ve todas las fincas."""
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get(f'{self.base_url_prod}by-farm/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        farm_ids = [str(item['farm_id']) for item in resp.data]
        self.assertIn(str(self.farm1.id), farm_ids)

    def test_admin_by_lot_without_filters_sees_all(self):
        """El administrador sin filtros ve todos los lotes."""
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get(f'{self.base_url_prod}by-lot/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        lot_ids = [str(item['lot_id']) for item in resp.data]
        self.assertIn(str(self.lot1_f1.id), lot_ids)

    def test_production_consolidation_multiple_harvests(self):
        """Múltiples registros de recolección se suman sin duplicarse."""
        HarvestRecord.objects.create(
            workday_detail=self.workday_detail,
            quantity_kg=Decimal('10.25'),
            time=time(14, 0)
        )
        self.client.force_authenticate(user=self.producer1)
        resp = self.client.get(f'{self.base_url_prod}by-farm/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        farm_data = next((item for item in resp.data if str(item['farm_id']) == str(self.farm1.id)), None)
        self.assertIsNotNone(farm_data)
        self.assertEqual(Decimal(str(farm_data['total_quantity_kg'])), Decimal('35.75'))
        self.assertEqual(farm_data['total_harvest_records'], 2)

    def test_production_filter_serializer_invalid_month(self):
        """Rechaza un mes inválido."""
        self.client.force_authenticate(user=self.producer1)
        resp = self.client.get(f'{self.base_url_prod}by-farm/?month=13')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_production_filter_serializer_invalid_year(self):
        """Rechaza un año fuera del rango permitido."""
        self.client.force_authenticate(user=self.producer1)
        resp = self.client.get(f'{self.base_url_prod}by-farm/?year=1800')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
