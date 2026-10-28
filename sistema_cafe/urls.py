from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include("apps.accounts.urls")),
    path('farms/', include("apps.farms.urls")),
    path('labor/', include("apps.labor.urls")),
    path('payroll/', include("apps.payroll.urls")),
    path('finance/', include("apps.finance.urls")),
    path('production/', include("apps.production.urls")),
]
