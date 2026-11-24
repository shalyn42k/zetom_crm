from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ClientsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "crm.clients"
    # claude — without this, Django's default AppConfig.verbose_name falls
    # back to self.label.title() (a plain string, not gettext) — same
    # English-regardless-of-locale bug as crm/users/apps.py and
    # crm/notification/apps.py.
    verbose_name = _("Clients")
