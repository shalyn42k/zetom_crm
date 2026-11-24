from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class StatusManagerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "crm.status_manager"
    # claude — without it the admin log/content types showed "Status_Manager"
    verbose_name = _("Status history")
    
