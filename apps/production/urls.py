from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import ProductionViewSet, SaleViewSet


# ---------------------------------------------------------------------------
# RUTAS DEL MÓDULO PRODUCTION
# ---------------------------------------------------------------------------
router = DefaultRouter()
router.register(r'sales', SaleViewSet, basename='sale')
router.register(r'production', ProductionViewSet, basename='production')

urlpatterns = [
    path('', include(router.urls)),
]
