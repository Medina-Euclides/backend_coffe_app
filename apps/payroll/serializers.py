from rest_framework import serializers

from .models import LaborPayment, Settlement, SettlementDetailHarvest, SettlementDetailWorkday


# ---------------------------------------------------------------------------
# SERIALIZADORES DE REPRESENTACIÓN (SOLO LECTURA / ESTRUCTURA)
# ---------------------------------------------------------------------------
# Solo definen cómo se representan los modelos en la API.


class SettlementDetailWorkdaySerializer(serializers.ModelSerializer):
    """Representa el detalle de liquidación por jornal."""
    class Meta:
        model = SettlementDetailWorkday
        fields = ("id", "settlement", "workday", "applied_daily_rate", "paid_amount")
        read_only_fields = ("id",)


class SettlementDetailHarvestSerializer(serializers.ModelSerializer):
    """Representa el detalle de liquidación por kilogramo."""
    class Meta:
        model = SettlementDetailHarvest
        fields = ("id", "settlement", "harvest_record", "paid_kg", "applied_kg_rate", "paid_amount")
        read_only_fields = ("id",)


class LaborPaymentSerializer(serializers.ModelSerializer):
    """Representa el pago registrado de una liquidación."""
    class Meta:
        model = LaborPayment
        fields = ("id", "settlement", "date", "amount_paid", "payment_method", "notes", "created_at")
        read_only_fields = ("id", "created_at")


class SettlementSerializer(serializers.ModelSerializer):
    """Representa la liquidación con sus detalles y pago."""
    workday_details = SettlementDetailWorkdaySerializer(many=True, read_only=True)
    harvest_details = SettlementDetailHarvestSerializer(many=True, read_only=True)
    payment = LaborPaymentSerializer(read_only=True)

    class Meta:
        model = Settlement
        fields = (
            "id",
            "worker",
            "farm",
            "start_date",
            "end_date",
            "total_calculated",
            "status",
            "created_at",
            "closed_at",
            "paid_at",
            "workday_details",
            "harvest_details",
            "payment",
        )
        read_only_fields = ("id", "total_calculated", "status", "created_at", "closed_at", "paid_at")


# ---------------------------------------------------------------------------
# SERIALIZADORES DE ENTRADA (SOLO VALIDACIÓN DE DATOS)
# ---------------------------------------------------------------------------
# Solo validan estructura de datos. La lógica va en services.py.


class AddWorkdayDetailSerializer(serializers.Serializer):
    """Valida IDs para añadir jornada por jornal."""
    settlement_id = serializers.UUIDField()
    workday_id = serializers.UUIDField()


class AddHarvestDetailSerializer(serializers.Serializer):
    """Valida IDs para añadir pesaje por kg."""
    settlement_id = serializers.UUIDField()
    harvest_record_id = serializers.UUIDField()


class CloseSettlementSerializer(serializers.Serializer):
    """Valida ID para cerrar liquidación."""
    settlement_id = serializers.UUIDField()


class PaySettlementSerializer(serializers.Serializer):
    """Valida datos para registrar pago."""
    settlement_id = serializers.UUIDField()
    date = serializers.DateField()
    amount_paid = serializers.DecimalField(max_digits=12, decimal_places=2)
    payment_method = serializers.ChoiceField(choices=LaborPayment.PaymentMethod.choices)
    notes = serializers.CharField(required=False, allow_blank=True)
