print("APPS.PY LOADED")

from django.apps import AppConfig

class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "users"

    def ready(self):
        print("READY() WORKS")
        import users.signals          
        import users.signals_profile 
