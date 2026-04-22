# Django imports
from django.apps import AppConfig


class NotificationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "crm.notification"
    label = "notification"
    verbose_name = "notifications"
