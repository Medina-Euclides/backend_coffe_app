import uuid

from django.db import models
from django.core.validators import MinValueValidator
from django.conf import settings


class OperatingExpense(models.Model):

    class Category(models.TextChoices):
        LABOR = "labor", "Mano de obra"
        INPUTS = "inputs", "Insumos agrícolas"
        TOOLS_MATERIALS = "tools_materials", "Herramientas y materiales"
        TRANSPORT = "transport", "Transporte"
        SERVICES = "services", "Servicios"
        OTHER = "other", "Otros"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    farm = models.ForeignKey(
        "farms.Farm",
        on_delete=models.PROTECT,
        related_name="operating_expenses",
    )

    labor_payment = models.OneToOneField(
        "payroll.LaborPayment",
        on_delete=models.PROTECT,
        related_name="operating_expense",
        null=True,
        blank=True,
    )

    date = models.DateField()

    concept = models.CharField(
        max_length=200,
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
    )

    category = models.CharField(
        max_length=30,
        choices=Category.choices,
        default=Category.OTHER,
    )

    notes = models.TextField(
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "Egreso operativo"
        verbose_name_plural = "Egresos operativos"

    def __str__(self):
        return f"{self.concept} - ${self.amount}"