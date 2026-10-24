from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import FarmView, LotView

router = DefaultRouter()
router.register(r'lots', LotView, basename='lot')
router.register(r'', FarmView, basename='farm')

urlpatterns = [
    path('', include(router.urls)),
]
