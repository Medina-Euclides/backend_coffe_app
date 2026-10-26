from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    LaborPaymentViewSet,
    SettlementDetailHarvestViewSet,
    SettlementDetailWorkdayViewSet,
    SettlementViewSet,
)

# ---------------------------------------------------------------------------
# RUTAS DEL MÓDULO DE PAYROLL
# ---------------------------------------------------------------------------
router = DefaultRouter()
router.register(r'settlements', SettlementViewSet, basename='settlement')
router.register(r'settlement-workdays', SettlementDetailWorkdayViewSet, basename='settlement-workday')
router.register(r'settlement-harvests', SettlementDetailHarvestViewSet, basename='settlement-harvest')
router.register(r'payments', LaborPaymentViewSet, basename='labor-payment')

urlpatterns = [
    path('', include(router.urls)),
]
