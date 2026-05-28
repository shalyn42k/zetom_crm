# Django imports
from django.apps import AppConfig
from django.conf import settings


class NotificationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "crm.notification"
    label = "notification"
    verbose_name = "notifications"

    # claude
    def ready(self):
        # claude — глобальный дефолт пагинации для всех ModelAdmin'ов
        # (включая Unfold, который наследуется от django.contrib.admin).
        # Один env-параметр PAGE_SIZE рулит и admin changelist'ами, и
        # кастомным inbox-paginator'ом в notification/views.py.
        # ModelAdmin'ы, которые явно задают свой `list_per_page` в коде,
        # переопределяют этот дефолт — это намеренно.
        from django.contrib.admin import ModelAdmin

        from . import signals  # noqa: F401
        ModelAdmin.list_per_page = settings.PAGE_SIZE
