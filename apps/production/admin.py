from django.contrib import admin
from .models import Sale


# ---------------------------------------------------------------------------
# ADMIN DEL MÓDULO PRODUCTION
# ---------------------------------------------------------------------------
@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    """Configuración del panel admin para ventas."""
    list_display = ("id", "farm", "sale_date", "coffee_type", "quantity_kg", "unit_price", "total_amount", "buyer")
    list_filter = ("coffee_type", "sale_date", "farm")
    search_fields = ("farm__name", "buyer", "notes")
    readonly_fields = ("id", "total_amount", "created_at", "updated_at")
    ordering = ("-sale_date",)
