import uuid

from django.db import models
from apps.farms.models import Farm


class Sale(models.Model):
    """Venta de café asociada a una finca del productor."""

    class CoffeeType(models.TextChoices):
        """Tipos de café comercializables."""
        PERGAMINO = "pergamino", "Pergamino"
        PASILLA = "pasilla", "Pasilla"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    farm = models.ForeignKey(
        Farm,
        on_delete=models.PROTECT,
        related_name="sales"
    )

    sale_date = models.DateField()

    coffee_type = models.CharField(
        max_length=30,
        choices=CoffeeType.choices
    )

    quantity_kg = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    buyer = models.CharField(
        max_length=150,
        blank=True,
        null=True
    )

    notes = models.TextField(
        blank=True
    )

    # Supresión lógica: conserva la venta en el histórico aunque se "elimine".
    is_active = models.BooleanField(
        default=True,
        help_text="Se desactiva en lugar de eliminar para conservar el histórico."
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        verbose_name = "Venta"
        verbose_name_plural = "Ventas"
        ordering = ["-sale_date"]

    def __str__(self):
        """Representación legible de la venta."""
        return (
            f"{self.get_coffee_type_display()} - "
            f"{self.quantity_kg} kg - {self.sale_date}"
        )
    