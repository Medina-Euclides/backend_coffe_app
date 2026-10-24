from django.contrib import admin
from .models import Farm, Lot


@admin.register(Farm)
class FarmAdmin(admin.ModelAdmin):
    list_display = ('name', 'id_productor', 'location', 'created_at')
    search_fields = ('name', 'id_productor__email')


@admin.register(Lot)
class LotAdmin(admin.ModelAdmin):
    list_display = ('name', 'id_farm', 'area_m2', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'id_farm__name')
