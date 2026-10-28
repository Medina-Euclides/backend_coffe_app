from django.apps import AppConfig


class FinanceConfig(AppConfig):
    name = 'apps.finance'

    def ready(self):
        from . import signals
