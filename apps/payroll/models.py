import uuid

from django.db import models
from django.db.models import Q, F

from apps.labor.models import Workday, HarvestRecord, Worker


# Representa la liquidación laboral de un trabajador en una finca.
class Settlement(models.Model):

    class Status(models.TextChoices):
        OPEN = "abierta", "Abierta (En cálculo)"
        CLOSED = "cerrada", "Cerrada (Pendiente de pago)"
        PAID = "pagada", "Pagada"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    worker = models.ForeignKey(Worker, on_delete=models.PROTECT, related_name="settlements")
    farm = models.ForeignKey("farms.Farm", on_delete=models.PROTECT, related_name="settlements")

    start_date = models.DateField()
    end_date = models.DateField()

    total_calculated = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    status = models.CharField(max_length=15, choices=Status.choices,default=Status.OPEN,)

    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Liquidación laboral"
        verbose_name_plural = "Liquidaciones laborales"
        ordering = ["-created_at"]

        constraints = [
            models.UniqueConstraint(
                fields=["worker", "farm"],
                condition=Q(status="abierta"),
                name="unique_open_settlement_per_worker_farm",
            ),
            models.CheckConstraint(
                condition=Q(total_calculated__gte=0),
                name="settlement_total_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(end_date__gte=F("start_date")),
                name="settlement_end_after_start",
            ),
        ]

    def __str__(self):
        return (
            f"Liquidación de {self.worker} "
            f"- {self.farm} "
            f"- {self.start_date} a {self.end_date}"
        )


# Registra las jornadas pagadas mediante la modalidad de jornal.
class SettlementDetailWorkday(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    settlement = models.ForeignKey(Settlement, on_delete=models.PROTECT, related_name="workday_details")
    workday = models.OneToOneField(Workday, on_delete=models.PROTECT, related_name="settlement_detail")

    applied_daily_rate = models.DecimalField(max_digits=12, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = "Detalle de liquidación por jornal"
        verbose_name_plural = "Detalles de liquidación por jornal"

        constraints = [
            models.CheckConstraint(
                condition=Q(applied_daily_rate__gte=0),
                name="workday_detail_rate_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(paid_amount__gte=0),
                name="workday_detail_amount_nonnegative",
            ),
        ]

    def __str__(self):
        return (
            f"{self.workday} "
            f"- {self.paid_amount}"
        )


# Registra los pesajes liquidados mediante la modalidad por kilogramo.
class SettlementDetailHarvest(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    settlement = models.ForeignKey(Settlement, on_delete=models.PROTECT, related_name="harvest_details")
    harvest_record = models.OneToOneField(HarvestRecord, on_delete=models.PROTECT, related_name="settlement_detail")

    paid_kg = models.DecimalField(max_digits=10, decimal_places=3)
    applied_kg_rate = models.DecimalField(max_digits=12, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = "Detalle de liquidación por kilogramo"
        verbose_name_plural = "Detalles de liquidación por kilogramo"

        constraints = [
            models.CheckConstraint(
                condition=Q(paid_kg__gt=0),
                name="harvest_detail_kg_positive",
            ),
            models.CheckConstraint(
                condition=Q(applied_kg_rate__gte=0),
                name="harvest_detail_rate_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(paid_amount__gte=0),
                name="harvest_detail_amount_nonnegative",
            ),
        ]

    def __str__(self):
        return (
            f"{self.paid_kg} kg "
            f"- {self.paid_amount}"
        )


# Registra el pago completo de una liquidación cerrada.
class LaborPayment(models.Model):

    class PaymentMethod(models.TextChoices):
        CASH = "efectivo", "Efectivo"
        TRANSFER = "transferencia", "Transferencia"
        OTHER = "otro", "Otro"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False,)
    settlement = models.OneToOneField(Settlement, on_delete=models.PROTECT, related_name="payment")

    date = models.DateField()
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2)

    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
    )

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Pago laboral"
        verbose_name_plural = "Pagos laborales"
        ordering = ["-date", "-created_at"]

        constraints = [
            models.CheckConstraint(
                condition=Q(amount_paid__gt=0),
                name="labor_payment_amount_positive",
            ),
        ]

    def __str__(self):
        return (
            f"Pago de {self.settlement.worker} "
            f"- {self.amount_paid}"
        )