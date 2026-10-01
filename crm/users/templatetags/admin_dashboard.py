from django import template
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.urls import reverse

from crm.clients.models import Client, Company
from crm.notification.utils import unread_count
from crm.status_manager.services.statuses import RequestStatus
from crm.users.utils import user_has_perm
from crm.zetom.models import RequestMain, RequestNull, StepNote, Wniosek, Zlecenie
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
        # claude — the tile links to the Klienci list, so it has to count what
        # that list shows: every firm plus every person. The person side used to
        # exclude a firm's contacts, matching the list, which excluded them too;
        # the list now shows all people, so the tile follows it.
        summary["clients"] = Company.objects.count() + Client.objects.count()

    if user_has_perm(user, "view_users"):
        summary["active_users"] = get_user_model().objects.filter(is_active=True).count()

    return summary


@register.simple_tag
def dashboard_personal_requests(user, limit=30):
    """Return the current user's request threads for the dashboard popover."""
    if not user.is_authenticated or not user_has_perm(user, "view_requests"):
        return []

    request_content_type = ContentType.objects.get_for_model(RequestMain)
    noted_request_ids = StepNote.objects.filter(
        target_content_type=request_content_type,
        author=user,
    ).values_list("target_object_id", flat=True)
    reminder_request_ids = StepNote.objects.filter(
        target_content_type=request_content_type,
        kind=StepNote.Kind.REMINDER,
        done_at__isnull=True,
        author=user,
    ).values_list("target_object_id", flat=True)
    requests = (
        RequestMain.objects.filter(
            Q(assigned_to=user)
            | Q(pk__in=noted_request_ids)
            | Q(pk__in=reminder_request_ids)
        )
        .distinct()
        .order_by("-updated_at", "-created_at")[:limit]
    )

    return [
        {
            "object": request,
            "name": request.full_name or request.company_name or str(request.pk),
            "url": reverse("admin:zetom_requestmain_change", args=[request.pk]),
        }
        for request in requests
    ]
