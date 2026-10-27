# Django imports
from django.apps import AppConfig
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class NotificationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "crm.notification"
    label = "notification"
    # claude — see crm/users/apps.py's identical fix: plain string, not
    # wrapped in gettext, so Unfold's breadcrumb rendered it in English.
    verbose_name = _("Notifications")

    # claude
    def ready(self):
        # claude — глобальный дефолт пагинации для всех ModelAdmin'ов
        # (включая Unfold, который наследуется от django.contrib.admin).
        # Один env-параметр PAGE_SIZE рулит и admin changelist'ами, и
        # кастомным inbox-paginator'ом в notification/views.py.
        # ModelAdmin'ы, которые явно задают свой `list_per_page` в коде,
        # переопределяют этот дефолт — это намеренно.
        from django.contrib.admin import ModelAdmin
        from unfold.admin import ModelAdmin as UnfoldModelAdmin

        from . import signals  # noqa: F401
        from .services.followup_scheduler import start_followup_scheduler
        ModelAdmin.list_per_page = settings.PAGE_SIZE
        # claude — Unfold wraps every changelist in Tailwind's `container`
        # (max-width 1536px, centred), so on a wide screen the table sat in
        # a narrow column with big empty gutters on both sides.
        # list_fullwidth is Unfold's own switch for that; same "global
        # default, a ModelAdmin may still override it" pattern as above.
        UnfoldModelAdmin.list_fullwidth = True
        start_followup_scheduler()
