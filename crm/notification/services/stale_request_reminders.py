"""Reminds staff about RequestMain rows nobody has picked up.

Mirrors followup_reminders.py's shape (same scheduler, same create_inapp
call), but the "due" signal is different: not an explicit next_contact_at
someone set, but the *absence* of any activity at all — no owner, no
StepNote — after STALE_REQUEST_REMINDER_DAYS. Guarded against re-sending
on every scheduler tick by checking for an existing Notification against
the same target with this template, rather than adding a new field to
RequestMain (StepNote has reminder_sent_at for the other reminder type;
RequestMain has no such column and doesn't need a migration for this).
"""
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from crm.notification.models import Notification, NotificationKind
from crm.notification.services import inapp_service
from crm.status_manager.services.statuses import RequestStatus
from crm.users.utils import user_has_perm
from crm.zetom.models import RequestMain, StepNote

TEMPLATE_NAME = "notification/inapp/staff/stale_request.txt"

# claude — closed/cancelled/deleted requests are done, not neglected;
# reminding about those would just be noise.
_TERMINAL_STATUSES = (RequestStatus.closed, RequestStatus.cancelled, RequestStatus.deleted)


def process_stale_requests(now=None):
    now = now or timezone.now()
    threshold = now - timezone.timedelta(days=settings.STALE_REQUEST_REMINDER_DAYS)
    epoch = timezone.datetime.fromisoformat(settings.STALE_REQUEST_REMINDER_EPOCH)
    if timezone.is_naive(epoch):
        epoch = timezone.make_aware(epoch)

    request_ct = ContentType.objects.get_for_model(RequestMain)
    already_reminded = set(
        Notification.objects.filter(
            target_content_type=request_ct,
            template_name=TEMPLATE_NAME,
        ).values_list("target_object_id", flat=True)
    )
    noted_request_ids = set(
        StepNote.objects.filter(
            target_content_type=request_ct,
        ).values_list("target_object_id", flat=True)
    )

    candidates = (
        RequestMain.objects.filter(created_at__lte=threshold, created_at__gte=epoch)
        .exclude(status__in=_TERMINAL_STATUSES)
        .exclude(pk__in=already_reminded)
        .exclude(pk__in=noted_request_ids)
        .filter(owners__isnull=True)
    )

    recipients = _resolve_recipients()
    if not recipients:
        return 0

    created_reminders = 0
    for request in candidates:
        notifications = inapp_service.create_inapp(
            kind=NotificationKind.SYSTEM,
            template_name=TEMPLATE_NAME,
            payload={
                "request_label": str(request),
                "created_at": timezone.localtime(request.created_at).strftime("%Y-%m-%d %H:%M"),
                "days_open": (now - request.created_at).days,
            },
            recipients=recipients,
            target=request,
        )
        if notifications:
            created_reminders += 1

    return created_reminders


# claude — no owner is assigned yet (that's the whole point), so there's no
# one obvious recipient the way followup_reminders.py has one via
# StepNote.author/target.owners. Notifies everyone who can actually act on
# a request (edit_requests), same permission the changelist itself is
# gated behind — small user base in practice (see crm/users/signals.py),
# a per-user check is plenty fast for a once-a-minute background job.
def _resolve_recipients():
    from django.contrib.auth.models import User

    return [
        u for u in User.objects.filter(is_active=True).select_related("profile")
        if user_has_perm(u, "edit_requests")
    ]
