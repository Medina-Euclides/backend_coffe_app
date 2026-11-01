from django.contrib import admin
from .models import (
    Worker,
    ActivityType,
    Workday,
    WorkdayWorker,
    WorkdayDetail,
    HarvestRecord,
)


@admin.register(Worker)
class WorkerAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'identification', 'producer', 'phone', 'is_active')
    list_filter = ('is_active', 'producer')
    search_fields = ('first_name', 'last_name', 'identification', 'producer__email')


@admin.register(ActivityType)
class ActivityTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'producer', 'is_harvest', 'description')
    list_filter = ('is_harvest', 'producer')
    search_fields = ('name',)


@admin.register(Workday)
class WorkdayAdmin(admin.ModelAdmin):
    list_display = ("farm", "producer", "date", "created_at")
    list_filter = ("producer", "farm", "date")
    search_fields = ("farm__name", "producer__email")


@admin.register(WorkdayWorker)
class WorkdayWorkerAdmin(admin.ModelAdmin):
    list_display = ("worker", "workday", "payment_mode", "agreed_rate", "settlement_status")
    list_filter = ("payment_mode", "settlement_status", "workday__farm")
    search_fields = ("worker__first_name", "worker__last_name", "workday__farm__name")


@admin.register(WorkdayDetail)
class WorkdayDetailAdmin(admin.ModelAdmin):
    list_display = ("activity_type", "workday_worker", "lot")


@admin.register(HarvestRecord)
class HarvestRecordAdmin(admin.ModelAdmin):
    list_display = ('workday_detail', 'quantity_kg', 'time', 'settlement_status')
    list_filter = ('settlement_status',)
