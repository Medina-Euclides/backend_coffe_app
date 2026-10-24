from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework.fields import empty

from .models import Farm, Lot

User = get_user_model()


class ModelDefaultBooleanField(serializers.BooleanField):
    default_empty_html = empty


class FarmSerializer(serializers.ModelSerializer):
    id_productor = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), required=False
    )
    producer_email = serializers.EmailField(source="id_productor.email", read_only=True)
    producer_name = serializers.CharField(source="id_productor.full_name", read_only=True)
    lots_count = serializers.IntegerField(source="lots.count", read_only=True)

    class Meta:
        model = Farm
        fields = (
            'id', 'id_productor', 'producer_email', 'producer_name',
            'name', 'location', 'description', 'lots_count',
            'created_at', 'updated_at'
        )
        read_only_fields = ('id', 'created_at', 'updated_at')

    def validate_id_productor(self, value):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if user and user.is_authenticated and not user.is_administrator:
            if value != user:
                raise serializers.ValidationError("Solo puedes registrar fincas a tu nombre.")
        return value


class LotSerializer(serializers.ModelSerializer):
    id_farm = serializers.PrimaryKeyRelatedField(queryset=Farm.objects.none())
    farm_name = serializers.CharField(source="id_farm.name", read_only=True)
    producer_email = serializers.EmailField(source="id_farm.id_productor.email", read_only=True)
    area_hectares = serializers.DecimalField(source="area_m2", max_digits=8, decimal_places=2, required=False, allow_null=True)
    is_active = ModelDefaultBooleanField(required=False)

    class Meta:
        model = Lot
        fields = (
            'id', 'id_farm', 'farm_name', 'producer_email',
            'name', 'coffee_variety', 'area_m2', 'area_hectares',
            'description', 'is_active', 'created_at', 'updated_at'
        )
        read_only_fields = ('id', 'created_at', 'updated_at')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if user and user.is_authenticated:
            if getattr(user, 'is_administrator', False):
                self.fields['id_farm'].queryset = Farm.objects.select_related('id_productor').all()
            else:
                self.fields['id_farm'].queryset = Farm.objects.filter(id_productor=user).select_related('id_productor')

    def validate_id_farm(self, value):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if user and user.is_authenticated and not getattr(user, 'is_administrator', False):
            if value.id_productor_id != user.id:
                raise serializers.ValidationError("La finca seleccionada no te pertenece.")
        return value
