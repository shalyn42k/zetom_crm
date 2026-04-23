print("APPS.PY LOADED")

from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "crm.users"
    label = "users"
    verbose_name = "users"

    def ready(self):
        print("READY() WORKS")
        import crm.users.signals
        import crm.users.signals_profile
