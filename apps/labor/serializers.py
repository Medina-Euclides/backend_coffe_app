from rest_framework import serializers

from apps.accounts.permissions import IsOwnerOrAdmin
from apps.farms.models import Lot
from .models import Worker, ActivityType, Workday, WorkdayDetail, HarvestRecord


class WorkerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Worker
        fields = ('id', 'producer', 'identification', 'first_name', 'last_name', 'phone', 'is_active')
        read_only_fields = ('id',)


class ActivityTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityType
        fields = ('id', 'producer', 'name', 'description', 'is_harvest')
        read_only_fields = ('id',)


class HarvestRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = HarvestRecord
        fields = ('id', 'workday_detail', 'quantity_kg', 'time', 'settlement_status')
        read_only_fields = ('id',)


class WorkdayDetailSerializer(serializers.ModelSerializer):
    harvest_records = HarvestRecordSerializer(many=True, read_only=True)

    class Meta:
        model = WorkdayDetail
        fields = ('id', 'activity_type', 'workday', 'lot', 'harvest_records')
        read_only_fields = ('id',)


class WorkdaySerializer(serializers.ModelSerializer):
    details = WorkdayDetailSerializer(many=True, read_only=True)
    worker_name = serializers.CharField(source='worker.__str__', read_only=True)

    class Meta:
        model = Workday
        fields = ('id', 'worker', 'worker_name', 'date', 'payment_mode', 'agreed_rate',
                  'settlement_status', 'created_at', 'details')
        read_only_fields = ('id', 'created_at')
