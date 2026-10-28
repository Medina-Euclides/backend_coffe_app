from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.payroll.models import LaborPayment

from .models import OperatingExpense


@receiver(post_save, sender=LaborPayment)
def create_labor_payment_expense(sender, instance, created, **kwargs):
    if not created:
        return

    settlement = instance.settlement
    worker = settlement.worker
    OperatingExpense.objects.get_or_create(
        labor_payment=instance,
        defaults={
            "farm": settlement.farm,
            "date": instance.date,
            "concept": f"Pago laboral a {worker}",
            "amount": instance.amount_paid,
            "category": OperatingExpense.Category.LABOR,
            "notes": instance.notes,
        },
    )
