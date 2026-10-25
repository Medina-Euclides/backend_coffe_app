from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    WorkerViewSet,
    ActivityTypeViewSet,
    WorkdayViewSet,
    WorkdayDetailViewSet,
    HarvestRecordViewSet,
)

router = DefaultRouter()
router.register(r'workers', WorkerViewSet, basename='worker')
router.register(r'activity-types', ActivityTypeViewSet, basename='activity-type')
router.register(r'workdays', WorkdayViewSet, basename='workday')
router.register(r'workday-details', WorkdayDetailViewSet, basename='workday-detail')
router.register(r'harvest-records', HarvestRecordViewSet, basename='harvest-record')

urlpatterns = [
    path('', include(router.urls)),
]
