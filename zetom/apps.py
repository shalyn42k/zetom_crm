from django.apps import AppConfig


class ZetomConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "zetom"
    verbose_name = "Zetom CRM"

    def ready(self):
        import zetom.signals
