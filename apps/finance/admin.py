from django.contrib import admin

from .models import OperatingExpense


@admin.register(OperatingExpense)
class OperatingExpenseAdmin(admin.ModelAdmin):
    list_display = ("date", "concept", "farm", "amount", "category", "labor_payment")
    list_filter = ("category", "farm", "date")
    search_fields = ("concept", "farm__name", "notes")
    readonly_fields = ("id", "created_at", "updated_at", "labor_payment")

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = super().get_readonly_fields(request, obj)
        if obj and obj.labor_payment_id:
            return tuple(field.name for field in self.model._meta.fields)
        return readonly_fields

    def has_delete_permission(self, request, obj=None):
        return False
