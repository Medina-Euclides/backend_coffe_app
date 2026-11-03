from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.farms.models import Farm

from .services import AnalyticsService


class AnalyticsFilterSerializer(serializers.Serializer):
    farm_id = serializers.UUIDField(required=False)
    period = serializers.ChoiceField(
        choices=("week", "month", "year"),
        default="month",
    )


class ExpenseCategorySerializer(serializers.Serializer):
    category = serializers.CharField()
    label = serializers.CharField()
    total_amount = serializers.DecimalField(max_digits=14, decimal_places=2)


class FinancialSummarySerializer(serializers.Serializer):
    sales_income = serializers.DecimalField(max_digits=14, decimal_places=2)
    total_expenses = serializers.DecimalField(max_digits=14, decimal_places=2)
    net_income = serializers.DecimalField(max_digits=14, decimal_places=2)


class LotProductionSerializer(serializers.Serializer):
    lot_id = serializers.UUIDField()
    lot_name = serializers.CharField()
    farm_id = serializers.UUIDField()
    farm_name = serializers.CharField()
    plant_count = serializers.IntegerField(allow_null=True)
    total_quantity_kg = serializers.DecimalField(max_digits=14, decimal_places=3)


class ProductionPeriodSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    total_quantity_kg = serializers.DecimalField(max_digits=14, decimal_places=3)


class ProductionPeriodsSerializer(serializers.Serializer):
    week = ProductionPeriodSerializer()
    month = ProductionPeriodSerializer()
    year = ProductionPeriodSerializer()


class ProductionSeriesPointSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    total_quantity_kg = serializers.DecimalField(max_digits=14, decimal_places=3)


class ProductionSeriesSerializer(serializers.Serializer):
    period = serializers.ChoiceField(choices=("week", "month", "year"))
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    total_quantity_kg = serializers.DecimalField(max_digits=14, decimal_places=3)
    points = ProductionSeriesPointSerializer(many=True)


class AnalyticsSummarySerializer(serializers.Serializer):
    farm_id = serializers.UUIDField(allow_null=True)
    farm_name = serializers.CharField(allow_null=True)
    period = serializers.ChoiceField(choices=("week", "month", "year"))
    expenses_by_category = ExpenseCategorySerializer(many=True)
    financial_summary = FinancialSummarySerializer()
    production_by_lot = LotProductionSerializer(many=True)
    production_by_period = ProductionPeriodsSerializer()
    production_series = ProductionSeriesSerializer()


class AnalyticsSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        filter_serializer = AnalyticsFilterSerializer(data=request.query_params)
        filter_serializer.is_valid(raise_exception=True)
        farm_id = filter_serializer.validated_data.get("farm_id")
        selected_farm = None

        if farm_id is not None:
            try:
                selected_farm = Farm.objects.select_related("id_productor").get(
                    id=farm_id
                )
            except Farm.DoesNotExist as error:
                raise NotFound("Finca no encontrada.") from error

            if (
                not getattr(request.user, "is_administrator", False)
                and selected_farm.id_productor_id != request.user.id
            ):
                raise PermissionDenied("No tienes permisos sobre esta finca.")

        result = AnalyticsService.get_summary(
            user=request.user,
            farm_id=farm_id,
            selected_farm=selected_farm,
            period=filter_serializer.validated_data["period"],
        )
        return Response(AnalyticsSummarySerializer(result).data)
