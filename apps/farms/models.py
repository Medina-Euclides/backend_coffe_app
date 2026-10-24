import uuid
from django.db import models
from django.conf import settings


class Farm(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_productor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='farms'
    )

    name = models.CharField(max_length=150)
    location = models.CharField(max_length=150, blank=True, null=True)
    description = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "finca"
        verbose_name_plural = "fincas"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Lot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_farm = models.ForeignKey(
        Farm,
        on_delete=models.PROTECT,
        related_name="lots"
    )

    name = models.CharField(max_length=150)
    coffee_variety = models.CharField(max_length=150, blank=True, null=True)
    area_m2 = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "lote"
        verbose_name_plural = "lotes"
        ordering = ["name"]

    def __str__(self):
        return f"{self.id_farm.name} - {self.name}"
