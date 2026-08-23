from django import template

from django.contrib.auth import get_user_model

from crm.notification.utils import unread_count
from crm.clients.models import Client
from crm.status_manager.services.statuses import RequestStatus
from crm.users.utils import user_has_perm
from crm.zetom.models import RequestMain, RequestNull, Wniosek, Zlecenie
from crm.zetom.services.visibility import visible_requests_for


register = template.Library()


@register.simple_tag
def has_crm_perm(user, perm_code):
    return user_has_perm(user, perm_code)


@register.simple_tag
def unread_inapp_count(user):
    return unread_count(user)


@register.simple_tag
def dashboard_summary(user):
    """Return permission-filtered CRM numbers for the admin home dashboard."""
    summary = {
        "inbox": unread_count(user),
        "validation": 0,
        "active_requests": 0,
        "orders": 0,
        "applications": 0,
        "clients": 0,
        "active_users": 0,
    }

    if user_has_perm(user, "view_requests"):
        validation_qs = visible_requests_for(
            user,
            RequestNull.objects.filter(status=RequestStatus.active),
        )
        active_qs = visible_requests_for(
            user,
            RequestMain.objects.filter(
                status__in=(RequestStatus.active, RequestStatus.open),
            ),
        )
        summary["validation"] = validation_qs.count()
        summary["active_requests"] = active_qs.count()
        summary["orders"] = Zlecenie.objects.count()
        summary["applications"] = Wniosek.objects.count()

    if user_has_perm(user, "view_clients"):
        summary["clients"] = Client.objects.count()

    if user_has_perm(user, "view_users"):
        summary["active_users"] = get_user_model().objects.filter(is_active=True).count()

    return summary
