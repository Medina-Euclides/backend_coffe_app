import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.farms.models import Farm, Lot


class Worker(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    producer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="workers",
    )
    identification = models.CharField(max_length=150, unique=True, blank=True, null=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=150, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    # Nulo en los trabajadores creados antes de agregar este campo.
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        verbose_name = "Trabajador"
        verbose_name_plural = "Trabajadores"
        ordering = ["first_name", "last_name"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class ActivityType(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    producer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="activity_types",
    )
    name = models.CharField(max_length=150)
    description = models.CharField(max_length=150, blank=True)
    is_harvest = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Tipo de actividad"
        verbose_name_plural = "Tipos de actividad"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Workday(models.Model):
    class Status(models.TextChoices):
        OPEN = "abierta", "Abierta"
        CLOSED = "cerrada", "Cerrada"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    producer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="workdays",
    )
    farm = models.ForeignKey(
        Farm,
        on_delete=models.PROTECT,
        related_name="workdays",
    )
    date = models.DateField()
    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.OPEN,
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Jornada laboral"
        verbose_name_plural = "Jornadas laborales"
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(
                fields=["producer", "farm", "date"],
                name="unique_workday_farm_date",
            ),
        ]

    def clean(self):
        if self.farm_id and self.producer_id and self.farm.id_productor_id != self.producer_id:
            raise ValidationError({"farm": "La finca debe pertenecer al productor de la jornada."})
        if self.date and self.date > timezone.localdate():
            raise ValidationError({"date": "No se pueden registrar jornadas con fecha futura."})

    @property
    def is_closed(self):
        return self.status == self.Status.CLOSED

    def __str__(self):
        return f"{self.farm} - {self.date}"


class WorkdayWorker(models.Model):
    class PaymentMode(models.TextChoices):
        DAILY = "jornal", "Por jornal"
        KILOGRAM = "kg", "Por kilogramo"

    class SettlementStatus(models.TextChoices):
        PENDING = "pendiente", "Pendiente"
        SETTLED = "liquidado", "Liquidado"
        CANCELED = "anulado", "Anulado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    worker = models.ForeignKey(
        Worker,
        on_delete=models.PROTECT,
        related_name="workday_participations",
    )
    workday = models.ForeignKey(
        Workday,
        on_delete=models.PROTECT,
        related_name="participants",
    )
    payment_mode = models.CharField(max_length=15, choices=PaymentMode.choices, default=PaymentMode.DAILY)
    agreed_rate = models.DecimalField(max_digits=12, decimal_places=2)
    settlement_status = models.CharField(
        max_length=30,
        choices=SettlementStatus.choices,
        default=SettlementStatus.PENDING,
    )

    class Meta:
        verbose_name = "Participación de trabajador en jornada"
        verbose_name_plural = "Participaciones de trabajadores en jornadas"
        constraints = [
            models.UniqueConstraint(
                fields=["worker", "workday"],
                name="unique_worker_workday",
            ),
            models.CheckConstraint(
                condition=Q(agreed_rate__gt=0),
                name="workday_worker_rate_positive",
            ),
            models.CheckConstraint(
                condition=Q(payment_mode__in=["jornal", "kg"]),
                name="workday_worker_mode_valid",
            ),
            models.CheckConstraint(
                condition=Q(settlement_status__in=["pendiente", "liquidado", "anulado"]),
                name="workday_worker_status_valid",
            ),
        ]

    def clean(self):
        if (
            self.worker_id
            and self.workday_id
            and self.worker.producer_id != self.workday.producer_id
        ):
            raise ValidationError({"worker": "El trabajador debe pertenecer al productor de la jornada."})

    @property
    def has_settlement_detail(self):
        return hasattr(self, "settlement_detail")

    @property
    def has_settled_harvest(self):
        return self.details.filter(
            harvest_records__settlement_detail__isnull=False
        ).exists()

    @property
    def is_locked(self):
        """Una participación liquidada, anulada o ya incluida en una liquidación no se edita."""
        return (
            self.settlement_status != self.SettlementStatus.PENDING
            or self.has_settlement_detail
            or self.has_settled_harvest
        )

    def __str__(self):
        return f"{self.worker} - {self.workday.date}"


class WorkdayDetail(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    activity_type = models.ForeignKey(
        ActivityType,
        on_delete=models.PROTECT,
        related_name="workday_details",
    )
    workday_worker = models.ForeignKey(
        WorkdayWorker,
        on_delete=models.PROTECT,
        related_name="details",
    )
    lot = models.ForeignKey(
        Lot,
        on_delete=models.PROTECT,
        related_name="workday_details",
    )

    class Meta:
        verbose_name = "Detalle de jornada laboral"
        verbose_name_plural = "Detalles de jornada laboral"

    def clean(self):
        if self.workday_worker_id and self.lot_id:
            if self.lot.id_farm_id != self.workday_worker.workday.farm_id:
                raise ValidationError({"lot": "El lote debe pertenecer a la finca de la jornada."})
            if not self.lot.is_active:
                raise ValidationError({"lot": "No se pueden registrar labores en un lote inactivo."})
        if self.workday_worker_id and self.activity_type_id:
            producer_id = self.workday_worker.workday.producer_id
            if self.activity_type.producer_id != producer_id:
                raise ValidationError(
                    {"activity_type": "La actividad debe pertenecer al productor de la jornada."}
                )
            if (
                self.workday_worker.payment_mode == WorkdayWorker.PaymentMode.KILOGRAM
                and not self.activity_type.is_harvest
            ):
                raise ValidationError(
                    {"activity_type": "La modalidad por kilogramo solo admite actividades de recolección."}
                )

    def __str__(self):
        return f"{self.activity_type} - {self.lot}"


class HarvestRecord(models.Model):
    class SettlementStatus(models.TextChoices):
        REGISTERED = "registrado", "Registrado"
        SETTLED = "liquidado", "Liquidado"
        CANCELED = "anulado", "Anulado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workday_detail = models.ForeignKey(
        WorkdayDetail,
        on_delete=models.PROTECT,
        related_name="harvest_records",
    )
    quantity_kg = models.DecimalField(max_digits=10, decimal_places=3)
    time = models.TimeField()
    settlement_status = models.CharField(
        max_length=30,
        choices=SettlementStatus.choices,
        default=SettlementStatus.REGISTERED,
    )

    class Meta:
        verbose_name = "Registro de recolección"
        verbose_name_plural = "Registros de recolección"
        ordering = ["time"]
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity_kg__gt=0),
                name="harvest_quantity_positive",
            ),
            models.CheckConstraint(
                condition=Q(settlement_status__in=["registrado", "liquidado", "anulado"]),
                name="harvest_status_valid",
            ),
        ]

    def clean(self):
        if self.workday_detail_id and not self.workday_detail.activity_type.is_harvest:
            raise ValidationError(
                {"workday_detail": "El pesaje debe corresponder a una actividad de recolección."}
            )

    @property
    def has_settlement_detail(self):
        return hasattr(self, "settlement_detail")

    @property
    def is_locked(self):
        """Un pesaje liquidado o ya incluido en una liquidación no se edita."""
        return (
            self.settlement_status != self.SettlementStatus.REGISTERED
            or self.has_settlement_detail
        )

    def __str__(self):
        return f"{self.quantity_kg} kg - {self.time}"
