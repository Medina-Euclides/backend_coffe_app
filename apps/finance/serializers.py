from rest_framework import serializers

from apps.farms.models import Farm

from .models import OperatingExpense


class OperatingExpenseSerializer(serializers.ModelSerializer):
    farm_name = serializers.CharField(source="farm.name", read_only=True)
    labor_payment = serializers.UUIDField(source="labor_payment_id", read_only=True)

    class Meta:
        model = OperatingExpense
        fields = (
            "id",
            "farm",
            "farm_name",
            "labor_payment",
            "date",
            "concept",
            "amount",
            "category",
            "notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            farms = Farm.objects.all()
            if not getattr(user, "is_administrator", False):
                farms = farms.filter(id_productor=user)
            self.fields["farm"].queryset = farms

    def validate(self, attrs):
        if self.instance and self.instance.labor_payment_id:
            raise serializers.ValidationError(
                "Los egresos generados por pagos laborales no se pueden modificar."
            )
        return attrs

    def validate_category(self, value):
        if value == OperatingExpense.Category.LABOR:
            raise serializers.ValidationError(
                "Los egresos de mano de obra se generan al registrar el pago en payroll."
            )
        return value
