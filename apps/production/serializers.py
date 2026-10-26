from decimal import Decimal

from rest_framework import serializers

from .models import Sale


# ---------------------------------------------------------------------------
# SERIALIZADORES DEL MÓDULO PRODUCTION
# ---------------------------------------------------------------------------
# Solo validan datos recibidos y definen la representación de los objetos.


class SaleSerializer(serializers.ModelSerializer):
    """Serializador para representar y validar ventas de café."""

    class Meta:
        model = Sale
        fields = (
            "id",
            "farm",
            "sale_date",
            "coffee_type",
            "quantity_kg",
            "unit_price",
            "total_amount",
            "buyer",
            "notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "total_amount", "created_at", "updated_at")

    def validate_quantity_kg(self, value):
        """Valida que la cantidad en kg sea mayor a cero."""
        if value is None or value <= 0:
            raise serializers.ValidationError("La cantidad en kg debe ser mayor a cero.")
        return value

    def validate_unit_price(self, value):
        """Valida que el precio por unidad sea mayor a cero."""
        if value is None or value <= 0:
            raise serializers.ValidationError("El precio unitario debe ser mayor a cero.")
        return value

    def validate(self, attrs):
        """Validación cruzada: calcula el valor total multiplicando cantidad por precio."""
        quantity_kg = attrs.get("quantity_kg", getattr(self.instance, "quantity_kg", None))
        unit_price = attrs.get("unit_price", getattr(self.instance, "unit_price", None))

        # Validar campos requeridos
        if quantity_kg is None:
            raise serializers.ValidationError({"quantity_kg": ["Este campo es requerido."]})
        if unit_price is None:
            raise serializers.ValidationError({"unit_price": ["Este campo es requerido."]})
        if "farm" not in attrs and not getattr(self.instance, "farm", None):
            raise serializers.ValidationError({"farm": ["Este campo es requerido."]})
        if "sale_date" not in attrs and not getattr(self.instance, "sale_date", None):
            raise serializers.ValidationError({"sale_date": ["Este campo es requerido."]})
        if "coffee_type" not in attrs and not getattr(self.instance, "coffee_type", None):
            raise serializers.ValidationError({"coffee_type": ["Este campo es requerido."]})

        # Calcular total_amount = cantidad_kg * precio_unitario
        attrs["total_amount"] = quantity_kg * unit_price
        return attrs


class ProductionFilterSerializer(serializers.Serializer):
    """Serializador para validar filtros de consolidación de producción."""

    farm_id = serializers.UUIDField(required=False)
    lot_id = serializers.UUIDField(required=False)
    year = serializers.IntegerField(required=False, min_value=1900, max_value=2100)
    month = serializers.IntegerField(required=False, min_value=1, max_value=12)


class FarmProductionSummarySerializer(serializers.Serializer):
    """Representación de producción consolidada por finca."""

    farm_id = serializers.UUIDField()
    farm_name = serializers.CharField()
    total_quantity_kg = serializers.DecimalField(max_digits=12, decimal_places=3)
    total_harvest_records = serializers.IntegerField()


class LotProductionSummarySerializer(serializers.Serializer):
    """Representación de producción consolidada por lote."""

    lot_id = serializers.UUIDField()
    lot_name = serializers.CharField()
    farm_id = serializers.UUIDField()
    farm_name = serializers.CharField()
    total_quantity_kg = serializers.DecimalField(max_digits=12, decimal_places=3)
    total_harvest_records = serializers.IntegerField()
