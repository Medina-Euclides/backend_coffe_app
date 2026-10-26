import uuid

from django.db import models
from apps.farms.models import Farm


class Sale(models.Model):

    class CoffeeType(models.TextChoices):
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
        return (
            f"{self.get_coffee_type_display()} - "
            f"{self.quantity_kg} kg - {self.sale_date}"
        )