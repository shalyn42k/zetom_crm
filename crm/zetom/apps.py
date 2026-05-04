# Django app imports
from django.apps import AppConfig

class ZetomConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "crm.zetom"
    label = "zetom"
    verbose_name = "Zetom CRM"

    def ready(self):
        import crm.status_manager.signals
