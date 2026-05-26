"""Inbox UI для inapp-уведомлений и POST-эндпоинты для пометки прочитанным.

Свои URL вне /admin/, шаблон extend'ит admin/base_site.html чтобы сохранить
sidebar/topbar Unfold. Layout — handoff V1 (см. design_handoff_notifications/).
"""
# Stdlib
from datetime import timedelta

# Django imports
from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

# Local imports
from crm.notification.models import Notification, NotificationKind
from crm.notification.services import inapp_service
from crm.notification.utils import render_notification, target_url
from crm.users.utils import user_has_perm

# claude — handoff V1 диктует 10 на страницу.
INBOX_PAGE_SIZE = 10

# claude — какие kind'ы вообще существуют, для chip-фильтра в шаблоне.
KIND_META = {
    NotificationKind.STATUS_CHANGE: {"color": "blue", "icon_class": "k-status", "icon_id": "ki-status"},
    NotificationKind.REVIEW_REQUEST: {"color": "amber", "icon_class": "k-review-req", "icon_id": "ki-review-req"},
    NotificationKind.REVIEW_RESOLVED: {"color": "green", "icon_class": "k-review-ok", "icon_id": "ki-review-ok"},
    NotificationKind.ASSIGNMENT: {"color": "purple", "icon_class": "k-assign", "icon_id": "ki-assign"},
    NotificationKind.SYSTEM: {"color": "slate", "icon_class": "k-system", "icon_id": "ki-system"},
}


# claude
def _initials(user):
    """Two letters max — first letter of first_name, first of last_name."""
    if not user:
        return ""
    parts = (user.first_name or "", user.last_name or "")
    s = "".join(p[:1] for p in parts if p).upper()
    return s or (user.username or "?")[:1].upper()


# claude
def _avatar_color(user):
    """Deterministic colour from a small palette so the same user always gets
    the same tile colour. Keeps the inbox visually stable across reloads."""
    palette = ["#3b82f6", "#7c3aed", "#16a34a", "#f59e0b", "#dc2626", "#0891b2"]
    if not user:
        return palette[0]
    return palette[user.pk % len(palette)]


# claude
def _day_bucket(dt, now):
    """Map a datetime into one of three day-bucket labels used by the layout."""
    today = now.date()
    if dt.date() == today:
        return "today"
    if dt.date() == today - timedelta(days=1):
        return "yesterday"
    if dt.date() > today - timedelta(days=7):
        return "earlier_week"
    return "older"


# claude
@staff_member_required
def inbox(request):
    """Render the full-fidelity inbox page (handoff V1).

    Query string params:
        filter=all|unread        — segmented control
        kind=<NotificationKind>  — single-select kind chip
        page=<n>                 — paginator page

    Pagination is server-side via Django's Paginator; counts for the
    All/Unread/kind chips are computed from the full per-user queryset so
    they don't shrink when a filter is active.
    """
    # claude — staff_member_required прокидывает login + is_staff. Permission
    # `view_inbox` (см. crm/users/signals.py) — дополнительный гейт, чтобы
    # админ мог отозвать inbox у конкретной роли через extra_permissions.
    if not user_has_perm(request.user, "view_inbox"):
        return HttpResponseForbidden("You don't have permission to view the inbox.")

    filter_value = request.GET.get("filter", "all")
    if filter_value not in ("all", "unread"):
        filter_value = "all"
    kind_filter = request.GET.get("kind") or "all"

    base_qs = Notification.objects.filter(recipient=request.user)
    qs = (
        base_qs.select_related("actor", "target_content_type")
        .order_by("-created_at")
    )
    if filter_value == "unread":
        qs = qs.filter(is_read=False)
    if kind_filter != "all" and kind_filter in NotificationKind.values:
        qs = qs.filter(kind=kind_filter)

    paginator = Paginator(qs, INBOX_PAGE_SIZE)
    page_number = request.GET.get("page") or 1
    page_obj = paginator.get_page(page_number)

    now = timezone.now()
    bucket_labels = {
        "today": "Today",
        "yesterday": "Yesterday",
        "earlier_week": "Earlier this week",
        "older": "Older",
    }
    # Build a flat list of dicts; the template walks it once and emits a
    # day-group header whenever the bucket changes. Pagination is done on
    # the queryset already, so buckets only describe the current page slice.
    items = []
    last_bucket = None
    for n in page_obj.object_list:
        bucket = _day_bucket(n.created_at, now)
        title, body = render_notification(n)
        kind_meta = KIND_META.get(n.kind, {"color": "slate", "icon_class": "k-system", "icon_id": "ki-system"})
        items.append({
            "id": n.id,
            "kind": n.kind,
            "kind_label": NotificationKind(n.kind).label if n.kind in NotificationKind.values else n.kind,
            "kind_color": kind_meta["color"],
            "kind_icon_class": kind_meta["icon_class"],
            "kind_icon_id": kind_meta["icon_id"],
            "is_read": n.is_read,
            "created_at": n.created_at,
            "actor": n.actor,
            "actor_initials": _initials(n.actor) if n.actor else "",
            "actor_color": _avatar_color(n.actor) if n.actor else "",
            "title": title,
            "body": body,
            "target_url": target_url(n),
            "request_label": (n.payload or {}).get("request_label", ""),
            "bucket": bucket,
            "bucket_first": bucket != last_bucket,
            "bucket_label": bucket_labels.get(bucket, ""),
        })
        last_bucket = bucket

    # Counters for the toolbar — independent of current filter so the UI
    # always shows "N total / M unread" regardless of what's filtered.
    total = base_qs.count()
    unread = base_qs.filter(is_read=False).count()

    # Per-kind counts for chip pills (computed from currently-filtered
    # filter_value but not kind, so user can see "if I switch to amber, how
    # many would I get").
    kind_counts_qs = base_qs
    if filter_value == "unread":
        kind_counts_qs = kind_counts_qs.filter(is_read=False)
    kind_counts = {k: 0 for k in NotificationKind.values}
    for row in kind_counts_qs.values("kind"):
        if row["kind"] in kind_counts:
            kind_counts[row["kind"]] += 1

    # claude — each_context populates `available_apps`, `site_header`, etc.
    # so the Unfold sidebar/topbar render the same as on every admin page.
    context = admin.site.each_context(request)
    context.update({
        "items": items,
        "page_obj": page_obj,
        "paginator": paginator,
        "filter_value": filter_value,
        "kind_filter": kind_filter,
        "kinds": [
            {
                "value": k,
                "label": NotificationKind(k).label,
                "color": KIND_META[k]["color"],
                "count": kind_counts[k],
            }
            for k in NotificationKind.values
        ],
        "total_count": total,
        "unread_count_total": unread,
        "title": "Notifications",
    })
    return render(request, "notification/inbox.html", context)


# claude
@require_POST
@login_required
def mark_read(request, pk):
    """Mark one notification as read, then redirect.

    Redirect priority: `?back=` query (only same-origin paths), GFK target,
    fallback to the inbox. Per handoff, default redirect goes to the
    notification target (`get_absolute_url()` of the linked object), so the
    user lands on the thing the notification was about.

    REVIEW_REQUEST is intentionally NOT marked here — dep_head must
    explicitly resolve (approve/reject) for the unread state to clear.
    The mark-as-read for that kind happens in resolve_review_action.
    """
    notification = get_object_or_404(Notification, pk=pk)
    if notification.recipient_id != request.user.id:
        return HttpResponseForbidden("Not your notification.")

    # claude — для REVIEW_REQUEST ни pin-чекмарка, ни клика по заголовку с
    # `?back=inbox` не должно "съедать" нотификацию: dep_head обязан попасть
    # на Req и осознанно принять решение через Resolve-модалку. Поэтому здесь
    # игнорируем mark_read И `back`, и сразу ведём на target.
    if notification.kind == NotificationKind.REVIEW_REQUEST:
        tgt = target_url(notification)
        if tgt:
            return redirect(tgt)
        return redirect(reverse("notification:inbox"))

    inapp_service.mark_read(notification, by_user=request.user)

    back = request.GET.get("back")
    if back and back.startswith("/"):
        return redirect(back)
    tgt = target_url(notification)
    if tgt:
        return redirect(tgt)
    return redirect(reverse("notification:inbox"))


# claude
@require_POST
@login_required
def mark_all_read(request):
    """Bulk mark every unread notification of the current user.

    REVIEW_REQUEST is excluded — by design, оно снимается только после
    Approve/Reject в Resolve-модалке на самом Req.
    """
    inapp_service.mark_all_read(
        request.user,
        exclude_kinds=[NotificationKind.REVIEW_REQUEST],
    )
    return redirect(reverse("notification:inbox"))
