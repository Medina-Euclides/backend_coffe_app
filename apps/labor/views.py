from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.accounts.permissions import IsOwnerOrAdmin
from apps.farms.models import Farm
from .models import Worker, ActivityType, Workday, WorkdayDetail, HarvestRecord
from .serializers import (
    WorkerSerializer,
    ActivityTypeSerializer,
    WorkdaySerializer,
    WorkdayDetailSerializer,
    HarvestRecordSerializer,
)


class BaseLaborViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]


class WorkerViewSet(BaseLaborViewSet):
    serializer_class = WorkerSerializer
    queryset = Worker.objects.select_related('producer').all()

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        if getattr(user, 'is_administrator', False):
            return queryset
        return queryset.filter(producer=user)

    def perform_create(self, serializer):
        user = self.request.user
        producer = serializer.validated_data.get('producer') or user
        if not getattr(user, 'is_administrator', False) and producer != user:
            producer = user
        serializer.save(producer=producer)


class ActivityTypeViewSet(BaseLaborViewSet):
    serializer_class = ActivityTypeSerializer
    queryset = ActivityType.objects.select_related('producer').all()

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        if getattr(user, 'is_administrator', False):
            return queryset
        return queryset.filter(producer=user)

    def perform_create(self, serializer):
        user = self.request.user
        producer = serializer.validated_data.get('producer') or user
        if not getattr(user, 'is_administrator', False) and producer != user:
            producer = user
        serializer.save(producer=producer)


class WorkdayViewSet(BaseLaborViewSet):
    serializer_class = WorkdaySerializer
    queryset = Workday.objects.select_related('worker', 'worker__producer').prefetch_related('details', 'details__harvest_records').all()

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        if getattr(user, 'is_administrator', False):
            return queryset
        return queryset.filter(worker__producer=user)


class WorkdayDetailViewSet(BaseLaborViewSet):
    serializer_class = WorkdayDetailSerializer
    queryset = WorkdayDetail.objects.select_related('activity_type', 'workday', 'lot', 'workday__worker__producer').prefetch_related('harvest_records').all()

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        if getattr(user, 'is_administrator', False):
            return queryset
        return queryset.filter(workday__worker__producer=user)


class HarvestRecordViewSet(BaseLaborViewSet):
    serializer_class = HarvestRecordSerializer
    queryset = HarvestRecord.objects.select_related('workday_detail', 'workday_detail__workday__worker__producer').all()

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        if getattr(user, 'is_administrator', False):
            return queryset
        return queryset.filter(workday_detail__workday__worker__producer=user)
