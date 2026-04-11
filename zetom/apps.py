from django.apps import AppConfig

class ZetomConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'zetom'

    def ready(self):
        import zetom.signals
