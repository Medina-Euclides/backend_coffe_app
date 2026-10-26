from django.contrib import admin

from .models import LaborPayment, Settlement, SettlementDetailHarvest, SettlementDetailWorkday


# Muestra liquidaciones en el panel de administración
@admin.register(Settlement)
class SettlementAdmin(admin.ModelAdmin):
    list_display = ("id", "worker", "farm", "start_date", "end_date", "total_calculated", "status")
    list_filter = ("status", "farm", "worker")
    search_fields = ("worker__first_name", "worker__last_name", "farm__name")
    readonly_fields = ("id", "created_at", "closed_at", "paid_at")


# Muestra detalles por jornal
@admin.register(SettlementDetailWorkday)
class SettlementDetailWorkdayAdmin(admin.ModelAdmin):
    list_display = ("id", "settlement", "workday", "applied_daily_rate", "paid_amount")
    search_fields = ("settlement__worker__first_name", "settlement__worker__last_name")


# Muestra detalles por cosecha (kg)
@admin.register(SettlementDetailHarvest)
class SettlementDetailHarvestAdmin(admin.ModelAdmin):
    list_display = ("id", "settlement", "harvest_record", "paid_kg", "applied_kg_rate", "paid_amount")
    search_fields = ("settlement__worker__first_name", "settlement__worker__last_name")


# Muestra pagos laborales
@admin.register(LaborPayment)
class LaborPaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "settlement", "date", "amount_paid", "payment_method", "created_at")
    list_filter = ("payment_method", "date")
    search_fields = ("settlement__worker__first_name", "settlement__worker__last_name")
