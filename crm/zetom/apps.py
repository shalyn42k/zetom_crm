# Django app imports
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ZetomConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "crm.zetom"
    label = "zetom"
    # claude — same fix already applied to every sibling app (users,
    # notification, clients): a plain string here renders unwrapped in
    # Unfold's breadcrumb (app_config.verbose_name) regardless of locale.
    # "Zetom CRM" is the brand name either way, so the Polish catalog entry
    # is an identity translation — this is about consistency/safety, not a
    # visible change.
    verbose_name = _("Zetom CRM")

    def ready(self):
        # Side-effect import — registers post_softdelete signal handlers.
        import crm.status_manager.signals  # noqa: F401
