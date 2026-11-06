import uuid

from django.conf import settings
from django.db import models


class SyncOperation(models.Model):
    """
    Registro de cada operación enviada desde un dispositivo que trabajó sin conexión.
    Garantiza idempotencia: si el dispositivo reenvía la misma operación (op_id),
    se devuelve el resultado guardado sin volver a aplicarla.
    """

    class Status(models.TextChoices):
        APPLIED = "applied", "Aplicada"
        REJECTED = "rejected", "Rechazada"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    op_id = models.UUIDField()
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sync_operations",
    )
    entity = models.CharField(max_length=50)
    action = models.CharField(max_length=30)
    object_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=Status.choices)
    http_status = models.PositiveSmallIntegerField(default=200)
    response = models.JSONField(default=dict, blank=True)
    client_created_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Operación sincronizada"
        verbose_name_plural = "Operaciones sincronizadas"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "op_id"], name="unique_sync_op_per_user"),
        ]

    def __str__(self):
        return f"{self.entity}.{self.action} ({self.status})"
