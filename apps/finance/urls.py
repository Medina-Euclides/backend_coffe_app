from rest_framework.routers import DefaultRouter

from .views import OperatingExpenseViewSet

router = DefaultRouter()
router.register("expenses", OperatingExpenseViewSet, basename="operating-expense")

urlpatterns = router.urls
