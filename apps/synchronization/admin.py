from django.contrib import admin

from .models import SyncOperation


@admin.register(SyncOperation)
class SyncOperationAdmin(admin.ModelAdmin):
    list_display = ("entity", "action", "object_id", "status", "http_status", "user", "created_at")
    list_filter = ("status", "entity", "action")
    search_fields = ("op_id", "object_id")
    readonly_fields = [field.name for field in SyncOperation._meta.fields]
