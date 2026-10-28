from rest_framework import serializers

from apps.farms.models import Farm
from apps.labor.models import Worker
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
        # La unicidad de la liquidación abierta se valida en validate() con un
        # mensaje de negocio claro (el constraint de BD queda como respaldo).
        validators = []

    def __init__(self, *args, **kwargs):
        """
        Restringe los trabajadores y fincas seleccionables al productor
        autenticado (aislamiento multi-tenant, SRS módulo 1, regla 7).
        """
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user and user.is_authenticated and not getattr(user, "is_administrator", False):
            self.fields["worker"].queryset = Worker.objects.filter(producer=user)
            self.fields["farm"].queryset = Farm.objects.filter(id_productor=user)

    def validate(self, attrs):
        """
        Valida la coherencia de la liquidación:
          - El periodo debe ser válido (SRS módulo 7).
          - El trabajador y la finca deben pertenecer al mismo productor.
          - Un trabajador solo puede tener una liquidación abierta a la vez
            (SRS módulo 7, regla 4).
        """
        start_date = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end_date = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start_date and end_date and end_date < start_date:
            raise serializers.ValidationError(
                {"end_date": "La fecha fin no puede ser anterior a la fecha de inicio."}
            )

        worker = attrs.get("worker", getattr(self.instance, "worker", None))
        farm = attrs.get("farm", getattr(self.instance, "farm", None))

        # Con detalles asociados no se puede cambiar el alcance de la
        # liquidación: los registros incluidos ya pertenecen a ese trabajador,
        # finca y periodo (integridad de la liquidación).
        if self.instance is not None:
            has_details = (
                self.instance.workday_details.exists()
                or self.instance.harvest_details.exists()
            )
            if has_details:
                for field in ("worker", "farm", "start_date", "end_date"):
                    if field in attrs and attrs[field] != getattr(self.instance, field):
                        raise serializers.ValidationError(
                            {
                                field: "No se puede modificar mientras la liquidación "
                                        "tenga detalles asociados."
                            }
                        )

        if worker and farm and farm.id_productor_id != worker.producer_id:
            raise serializers.ValidationError(
                {"farm": "La finca debe pertenecer al mismo productor que el trabajador."}
            )

        if worker:
            open_settlements = Settlement.objects.filter(
                worker=worker, status=Settlement.Status.OPEN
            )
            if self.instance is not None:
                open_settlements = open_settlements.exclude(pk=self.instance.pk)
            if open_settlements.exists():
                raise serializers.ValidationError(
                    {"worker": "El trabajador ya tiene una liquidación abierta. "
                               "Ciérrela antes de crear una nueva liquidación."}
                )

        return attrs


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
