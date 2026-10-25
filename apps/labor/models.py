
import uuid
from django.conf import settings
from django.db import models
from apps.farms.models import Lot


# Registra a los trabajadores del productor.
class Worker(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    producer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="workers")

    identification = models.CharField(max_length=150, unique=True, blank=True, null=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=150, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Trabajador"
        verbose_name_plural = "Trabajadores"
        ordering = ["first_name", "last_name"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


# Clasifica las actividades laborales.
class ActivityType(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    producer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="activity_types")

    name = models.CharField(max_length=150)
    description = models.CharField(max_length=150, blank=True)
    is_harvest = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Tipo de actividad"
        verbose_name_plural = "Tipos de actividad"
        ordering = ["name"]

    def __str__(self):
        return self.name

# Jornada diaria de un trabajador.
class Workday(models.Model):

    class PaymentMode(models.TextChoices):
        DAILY = "jornal", "Por jornal"
        KILOGRAM = "kg", "Por kilogramo"

    class SettlementStatus(models.TextChoices):
        PENDING = "pendiente", "Pendiente"
        SETTLED = "liquidada", "Liquidada"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    worker = models.ForeignKey(Worker, on_delete=models.PROTECT, related_name="workdays")

    date = models.DateField()
    payment_mode = models.CharField(max_length=15, choices=PaymentMode.choices, default=PaymentMode.DAILY)
    agreed_rate = models.DecimalField(max_digits=12, decimal_places=2)
    settlement_status = models.CharField(max_length=30, choices=SettlementStatus.choices, default=SettlementStatus.PENDING)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Jornada"
        verbose_name_plural = "Jornadas"
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(
                fields=["worker", "date"],
                name="unique_workday_per_worker_date",
            )
        ]

    def __str__(self):
        return f"{self.worker} - {self.date}"


# Actividad, lote dentro de una jornada.
class WorkdayDetail(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    activity_type = models.ForeignKey(ActivityType, on_delete=models.PROTECT, related_name="workday_details",)
    workday = models.ForeignKey(Workday, on_delete=models.CASCADE, related_name="details",)
    lot = models.ForeignKey(Lot, on_delete=models.PROTECT, related_name="workday_details",)

    class Meta:
        verbose_name = "Detalle_jornada"
        verbose_name_plural = "Detalle_jornadas"

    def __str__(self):
        return f"{self.activity_type} - {self.lot}"


# Cantidad de café recolectada en un detalle.
class HarvestRecord(models.Model):
    class SettlementStatus(models.TextChoices):
        PENDING = "pendiente", "Pendiente"
        SETTLED = "liquidada", "Liquidada"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workday_detail = models.ForeignKey(WorkdayDetail, on_delete=models.PROTECT, related_name="harvest_records")

    quantity_kg = models.DecimalField(max_digits=10, decimal_places=3)
    time = models.TimeField()
    settlement_status = models.CharField(max_length=30, choices=SettlementStatus.choices, default=SettlementStatus.PENDING)

    class Meta:
        verbose_name = "Registro_recoleccion"
        verbose_name_plural = "Registro_recolecciones"
        ordering = ["time"]

    def __str__(self):
        return f"{self.quantity_kg} kg - {self.time}"
