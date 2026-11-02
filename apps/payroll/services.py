# ---------------------------------------------------------------------------
# SERVICIOS DE NEGOCIO - MÓDULO PAYROLL
# ---------------------------------------------------------------------------
# Aquí va toda la lógica: búsqueda de registros elegibles, cálculos,
# validaciones complejas de negocio y ejecución de operaciones (añadir detalles,
# cerrar liquidación, registrar pago). Los serializers solo validan datos
# recibidos; las vistas solo reciben peticiones, invocan servicios y devuelven
# respuesta HTTP.

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.labor.models import HarvestRecord, WorkdayWorker
from .models import LaborPayment, Settlement, SettlementDetailHarvest, SettlementDetailWorkday


class PayrollService:
    """Servicio con operaciones de liquidación laboral."""

    @staticmethod
    def add_workday_to_settlement(*, settlement_id, workday_worker_id):
        """Añade una participación diaria con modalidad jornal a una liquidación abierta."""
        # Buscar liquidación
        try:
            settlement = Settlement.objects.select_related("worker", "farm").get(
                id=settlement_id
            )
        except Settlement.DoesNotExist:
            raise ValueError("Liquidación no encontrada.")

        # Buscar participación
        try:
            workday_worker = (
                WorkdayWorker.objects.select_related("worker", "workday")
                .get(id=workday_worker_id)
            )
        except WorkdayWorker.DoesNotExist:
            raise ValueError("Participación de jornada no encontrada.")
        workday = workday_worker.workday

        if workday_worker.worker_id != settlement.worker_id:
            raise ValueError("La participación debe pertenecer al trabajador de la liquidación.")
        if workday.farm_id != settlement.farm_id:
            raise ValueError("La participación debe pertenecer a la finca de la liquidación.")

        # Validar periodo
        if workday.date < settlement.start_date or workday.date > settlement.end_date:
            raise ValueError("La jornada debe estar dentro del período de la liquidación.")

        # Validar modalidad (solo jornal)
        if workday_worker.payment_mode != WorkdayWorker.PaymentMode.DAILY:
            raise ValueError("Solo se pueden añadir participaciones con modalidad jornal.")

        # Validar estado
        if settlement.status != Settlement.Status.OPEN:
            raise ValueError("Solo se pueden añadir detalles a liquidaciones abiertas.")

        # Validar que la jornada no haya sido liquidada previamente
        # (SRS módulo 7, regla 3: un registro no puede estar en dos liquidaciones).
        if workday_worker.settlement_status == WorkdayWorker.SettlementStatus.CANCELED:
            raise ValueError("Esta participación fue anulada.")
        if workday_worker.settlement_status == WorkdayWorker.SettlementStatus.SETTLED:
            raise ValueError("Esta participación ya fue liquidada previamente.")
        if SettlementDetailWorkday.objects.filter(workday_worker=workday_worker).exists():
            raise ValueError("Esta participación ya fue incluida en una liquidación.")

        # Calcular y crear detalle
        applied_rate = workday_worker.agreed_rate
        paid_amount = applied_rate  # Por jornal
        detail = SettlementDetailWorkday.objects.create(
            settlement=settlement,
            workday_worker=workday_worker,
            applied_daily_rate=applied_rate,
            paid_amount=paid_amount,
        )
        return detail

    @staticmethod
    def add_harvest_to_settlement(*, settlement_id, harvest_record_id):
        """
        Añade un registro de cosecha/pesaje por kg a una liquidación abierta.
        Valida pertenencia, periodo, modalidad y duplicados. Calcula monto.
        """
        # Buscar liquidación
        try:
            settlement = Settlement.objects.select_related("worker", "farm").get(
                id=settlement_id
            )
        except Settlement.DoesNotExist:
            raise ValueError("Liquidación no encontrada.")

        # Buscar cosecha
        try:
            harvest = (
                HarvestRecord.objects.select_related(
                    "workday_detail__workday_worker__worker",
                    "workday_detail__workday_worker__workday",
                    "workday_detail__lot__id_farm",
                ).get(id=harvest_record_id)
            )
        except HarvestRecord.DoesNotExist:
            raise ValueError("Registro de cosecha no encontrado.")

        workday_worker = harvest.workday_detail.workday_worker
        workday = workday_worker.workday
        lot_farm = getattr(harvest.workday_detail.lot, "id_farm", None)

        # Validaciones
        if workday_worker.worker_id != settlement.worker_id:
            raise ValueError("El pesaje debe pertenecer al trabajador de la liquidación.")
        if workday.farm_id != settlement.farm_id or not lot_farm or lot_farm.id != settlement.farm_id:
            raise ValueError("El pesaje debe pertenecer a la finca de la liquidación.")
        if workday.date < settlement.start_date or workday.date > settlement.end_date:
            raise ValueError("El pesaje debe estar dentro del período de la liquidación.")
        if workday_worker.payment_mode != WorkdayWorker.PaymentMode.KILOGRAM:
            raise ValueError("Solo se pueden añadir pesajes relacionados con jornadas de modalidad kg.")
        if settlement.status != Settlement.Status.OPEN:
            raise ValueError("Solo se pueden añadir detalles a liquidaciones abiertas.")
        # SRS módulo 7, regla 3: un pesaje no puede estar en dos liquidaciones.
        if harvest.settlement_status == HarvestRecord.SettlementStatus.CANCELED:
            raise ValueError("Este pesaje fue anulado.")
        if harvest.settlement_status == HarvestRecord.SettlementStatus.SETTLED:
            raise ValueError("Este pesaje ya fue liquidado previamente.")
        if SettlementDetailHarvest.objects.filter(harvest_record=harvest).exists():
            raise ValueError("Este pesaje ya fue incluido en una liquidación.")

        # Calcular y crear detalle
        paid_kg = harvest.quantity_kg
        applied_kg_rate = workday_worker.agreed_rate
        paid_amount = paid_kg * applied_kg_rate
        detail = SettlementDetailHarvest.objects.create(
            settlement=settlement,
            harvest_record=harvest,
            paid_kg=paid_kg,
            applied_kg_rate=applied_kg_rate,
            paid_amount=paid_amount,
        )
        return detail

    @staticmethod
    @transaction.atomic
    def close_settlement(*, settlement_id):
        """
        Cierra una liquidación abierta: suma detalles, calcula total,
        pasa a SETTLED y marca jornadas/cosechas como liquidadas.
        """
        try:
            settlement = Settlement.objects.get(id=settlement_id)
        except Settlement.DoesNotExist:
            raise ValueError("Liquidación no encontrada.")

        if settlement.status != Settlement.Status.OPEN:
            raise ValueError("Solo se pueden cerrar liquidaciones abiertas.")

        # Calcular total
        total_workday = Decimal("0")
        total_harvest = Decimal("0")
        for wd in settlement.workday_details.select_related("workday_worker").all():
            total_workday += wd.paid_amount
        for hd in settlement.harvest_details.select_related("harvest_record").all():
            total_harvest += hd.paid_amount
        total = total_workday + total_harvest

        # Actualizar liquidación
        settlement.total_calculated = total
        settlement.status = Settlement.Status.SETTLED
        settlement.closed_at = timezone.now()
        settlement.save(update_fields=["total_calculated", "status", "closed_at"])

        # Marcar como liquidados
        for wd in settlement.workday_details.select_related("workday_worker").all():
            wd.workday_worker.settlement_status = WorkdayWorker.SettlementStatus.SETTLED
            wd.workday_worker.save(update_fields=["settlement_status"])

        for hd in settlement.harvest_details.select_related(
            "harvest_record__workday_detail__workday_worker"
        ).all():
            harvest = hd.harvest_record
            harvest.settlement_status = HarvestRecord.SettlementStatus.SETTLED
            harvest.save(update_fields=["settlement_status"])

        affected_participations = {
            detail.harvest_record.workday_detail.workday_worker_id
            for detail in settlement.harvest_details.select_related(
                "harvest_record__workday_detail"
            )
        }
        for participation in WorkdayWorker.objects.filter(
            id__in=affected_participations,
            settlement_status=WorkdayWorker.SettlementStatus.PENDING,
        ):
            has_pending_harvest = HarvestRecord.objects.filter(
                workday_detail__workday_worker=participation,
                settlement_status=HarvestRecord.SettlementStatus.REGISTERED,
            ).exists()
            if not has_pending_harvest:
                participation.settlement_status = WorkdayWorker.SettlementStatus.SETTLED
                participation.save(update_fields=["settlement_status"])
        return settlement

    @staticmethod
    @transaction.atomic
    def pay_settlement(
        *, settlement_id, date, amount_paid, payment_method, notes=""
    ):
        """
        Registra pago de una liquidación cerrada. Valida monto exacto
        y que no exista pago previo. Pasa a PAID.
        """
        try:
            settlement = Settlement.objects.get(id=settlement_id)
        except Settlement.DoesNotExist:
            raise ValueError("Liquidación no encontrada.")

        if settlement.status != Settlement.Status.SETTLED:
            raise ValueError("El pago debe realizarse solo sobre una liquidación cerrada.")
        if amount_paid != settlement.total_calculated:
            raise ValueError("El importe pagado debe corresponder al total calculado de la liquidación.")
        if LaborPayment.objects.filter(settlement=settlement).exists():
            raise ValueError("Esta liquidación ya tiene un pago registrado.")

        payment = LaborPayment.objects.create(
            settlement=settlement,
            date=date,
            amount_paid=amount_paid,
            payment_method=payment_method,
            notes=notes or "",
        )
        settlement.status = Settlement.Status.PAID
        settlement.paid_at = timezone.now()
        settlement.save(update_fields=["status", "paid_at"])
        return payment
