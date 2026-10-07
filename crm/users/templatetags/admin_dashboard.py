from datetime import timedelta

from django import template
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from crm.clients.models import Client, Company
from crm.notification.utils import unread_count
from crm.status_manager.services.statuses import RequestStatus
from crm.users.utils import user_has_perm
from crm.zetom.models import (
    DepartmentsVariants, Oferta, RequestMain, RequestNull, StepNote, Wniosek,
    Zlecenie,
)
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
        "offers": 0,
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
        summary["offers"] = Oferta.objects.count()
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
        .prefetch_related("assigned_to")
        .order_by("-updated_at", "-created_at")[:limit]
    )

    open_reminder_ids = set(reminder_request_ids)
    department_labels = dict(DepartmentsVariants.choices)
    items = []
    for request in requests:
        contact_name = request.full_name
        company_name = request.company_name or ""
        display_name = contact_name or company_name or f"#{request.pk}"
        phone = str(request.phone or "")
        email = request.email or ""
        search_haystack = " ".join(
            filter(None, (display_name, company_name, phone, email, str(request.pk)))
        ).lower()
        items.append(
            {
                "object": request,
                "name": display_name,
                "company": company_name if contact_name else "",
                "phone": phone,
                "email": email,
                "status": request.status,
                "status_label": request.get_status_display(),
                "source_label": request.get_source_display(),
                "departments": [
                    str(department_labels.get(code, code))
                    for code in (request.departments or [])
                ],
                "updated_at": request.updated_at,
                "is_assigned": any(u.pk == user.pk for u in request.assigned_to.all()),
                "has_reminder": request.pk in open_reminder_ids,
                "search": search_haystack,
                "url": reverse("admin:zetom_requestmain_change", args=[request.pk]),
            }
        )
    return items


@register.simple_tag
def personal_request_statuses(personal_requests):
    """Unique statuses present in the personal list, in RequestStatus order."""
    present = {item["status"] for item in personal_requests}
    return [
        (code, str(label)) for code, label in RequestStatus.choices if code in present
    ]


@register.simple_tag
def dashboard_weekly_stats(user):
    """Weekly activity numbers for the current employee's dashboard panel."""
    empty = {"has_data": False, "updated": 0, "notes": 0, "reminders": 0, "days": []}
    if not user.is_authenticated or not user_has_perm(user, "view_requests"):
        return empty

    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=7)

    visible_main = visible_requests_for(user, RequestMain.objects.all())
    updated = visible_main.filter(
        updated_at__date__gte=week_start, updated_at__date__lt=week_end
    ).count()
    updated_prev = visible_main.filter(
        updated_at__date__gte=week_start - timedelta(days=7),
        updated_at__date__lt=week_start,
    ).count()

    notes_qs = StepNote.objects.filter(
        author=user,
        created_at__date__gte=week_start,
        created_at__date__lt=week_end,
    )
    notes = notes_qs.count()
    reminders = notes_qs.filter(kind=StepNote.Kind.REMINDER).count()

    request_ct = ContentType.objects.get_for_model(RequestMain)
    day_rows = (
        notes_qs.filter(target_content_type=request_ct)
        .values_list("target_object_id", "created_at")
        .order_by("created_at")
    )
    touched = {}
    for request_id, created_at in day_rows:
        touched.setdefault(request_id, set()).add(timezone.localtime(created_at).date())
    day_counts = [0] * 7
    for dates in touched.values():
        for date_value in dates:
            if week_start <= date_value < week_end:
                day_counts[date_value.weekday()] += 1

    day_names = [
        str(label)
        for label in (_("Mon"), _("Tue"), _("Wed"), _("Thu"), _("Fri"), _("Sat"), _("Sun"))
    ]
    max_count = max(day_counts) or 0
    days = [
        {
            "label": day_names[index],
            "count": count,
            "percent": round(count / max_count * 100) if max_count else 0,
            "is_today": index == today.weekday(),
        }
        for index, count in enumerate(day_counts)
    ]

    delta = updated - updated_prev
    best = None
    if max_count:
        best = {
            "label": day_names[day_counts.index(max_count)],
            "count": max_count,
        }

    return {
        "has_data": True,
        "week_start": week_start,
        "week_end": week_end - timedelta(days=1),
        "updated": updated,
        "updated_prev": updated_prev,
        "delta_abs": abs(delta),
        "delta_dir": "up" if delta > 0 else ("down" if delta < 0 else "flat"),
        "notes": notes,
        "reminders": reminders,
        "days": days,
        "best": best,
    }
