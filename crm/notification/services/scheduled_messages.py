# claude
"""Messages and reminders staff write by hand: to the client, to chosen
colleagues, or to everyone holding a role. Sent now or at `send_at`.

Delivery goes through the same two channels as every other notification
(inapp_service for the inbox, mail_service for email, both logged), and
respects NotificationPreference for staff recipients. The client branch
has no preferences — the author decided to write to them.

`process_due_messages` runs on the followup scheduler tick (and in the
create_followup_reminders command), so a reminder set for tomorrow 9:00
leaves within one tick of that time.
"""
import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone

from crm.notification.models import (
    MessageAudience, MessageChannel, MessageStatus, NotificationKind,
    ScheduledMessage,
)
from crm.notification.services import inapp_service, mail_service
from crm.notification.services.preferences import filter_email, filter_inapp

logger = logging.getLogger(__name__)
User = get_user_model()

INAPP_TEMPLATE = "notification/inapp/staff/message.txt"
STAFF_MAIL_TEMPLATE = "notification/mail/staff/message.txt"
CLIENT_MAIL_TEMPLATE = "notification/mail/client/message.txt"


def schedule_message(
    *,
    author,
    audience,
    subject,
    body,
    channel=MessageChannel.INAPP,
    send_at=None,
    users=(),
    roles=(),
    client_email="",
    target=None,
):
    """Create a ScheduledMessage and deliver it right away if it is due.

    Permission checks belong to the caller (the view knows who is asking);
    this only enforces that the message has somewhere to go.
    """
    now = timezone.now()
    if audience == MessageAudience.CLIENT:
        # A client has no inbox — email is the only possible channel.
        channel = MessageChannel.EMAIL
        if not client_email:
            raise ValueError("client_email is required for a client message")
    message = ScheduledMessage(
        author=author,
        audience=audience,
        channel=channel,
        recipient_roles=list(roles) if audience == MessageAudience.ROLES else [],
        client_email=client_email if audience == MessageAudience.CLIENT else "",
        subject=subject.strip(),
        body=body.strip(),
        send_at=send_at or now,
    )
    if target is not None:
        message.target = target
    message.save()
    if audience == MessageAudience.USERS:
        message.recipient_users.set(users)

    if message.send_at <= now:
        deliver(message, now=now)
        message.refresh_from_db()
    return message


def cancel_message(message):
    """Cancel a message that has not left yet. Returns True if it was cancelled."""
    updated = ScheduledMessage.objects.filter(
        pk=message.pk, status=MessageStatus.PENDING,
    ).update(status=MessageStatus.CANCELLED)
    return bool(updated)


def resolve_staff_recipients(message):
    """Active users the message is addressed to (before preferences)."""
    if message.audience == MessageAudience.USERS:
        qs = message.recipient_users.filter(is_active=True)
    elif message.audience == MessageAudience.ROLES:
        roles = list(message.recipient_roles or [])
        role_filter = Q(profile__role__code__in=roles)
        if "admin" in roles:
            role_filter |= Q(is_superuser=True)
        qs = User.objects.filter(role_filter, is_active=True)
    else:
        return []
    users = list(qs.distinct())
    # The author already knows what they wrote.
    return [u for u in users if u.pk != message.author_id]


def deliver(message, now=None):
    """Send one pending message. Locks the row so two scheduler ticks (or a
    tick racing an immediate send) can never deliver it twice."""
    now = now or timezone.now()
    with transaction.atomic():
        locked = ScheduledMessage.objects.select_for_update().filter(
            pk=message.pk, status=MessageStatus.PENDING,
        ).first()
        if locked is None:
            return 0
        try:
            count = _send(locked)
        except Exception as exc:  # never let one message kill the scheduler loop
            logger.exception("scheduled message %s failed", locked.pk)
            locked.status = MessageStatus.FAILED
            locked.status_reason = str(exc)[:1000]
            locked.save(update_fields=["status", "status_reason"])
            return 0

        locked.recipients_count = count
        locked.sent_at = now
        if count:
            locked.status = MessageStatus.SENT
        else:
            locked.status = MessageStatus.FAILED
            locked.status_reason = "No recipients accepted this message."
        locked.save(update_fields=["status", "status_reason", "sent_at", "recipients_count"])
        return count


def process_due_messages(now=None):
    """Deliver every pending message whose time has come. Returns how many left."""
    now = now or timezone.now()
    due = ScheduledMessage.objects.filter(
        status=MessageStatus.PENDING, send_at__lte=now,
    ).order_by("send_at")
    sent = 0
    for message in due:
        if deliver(message, now=now):
            sent += 1
    return sent


def _context(message):
    target = message.target
    return {
        "message": message,
        "subject": message.subject,
        "body": message.body,
        "author": _author_name(message.author),
        "target_label": str(target) if target is not None else "",
    }


def _author_name(user):
    if user is None:
        return "system"
    return user.get_full_name() or user.get_username()


def _send(message):
    if message.audience == MessageAudience.CLIENT:
        body = render_to_string(CLIENT_MAIL_TEMPLATE, _context(message))
        records = mail_service.send_to_client(
            to=message.client_email,
            subject=message.subject,
            body=body,
            template_name=CLIENT_MAIL_TEMPLATE,
            payload={"scheduled_message_id": message.pk},
            actor=message.author,
        )
        return sum(1 for r in records if r.status == "SENT")

    recipients = resolve_staff_recipients(message)
    delivered = set()

    if message.channel in (MessageChannel.INAPP, MessageChannel.BOTH):
        inbox_users = filter_inapp(recipients, NotificationKind.MESSAGE)
        inapp_service.create_inapp(
            kind=NotificationKind.MESSAGE,
            template_name=INAPP_TEMPLATE,
            payload={
                "subject": message.subject,
                "body": message.body[:1000],
                "author": _author_name(message.author),
                "target_label": _context(message)["target_label"],
            },
            recipients=inbox_users,
            actor=message.author,
            target=message.target,
        )
        delivered.update(u.pk for u in inbox_users)

    if message.channel in (MessageChannel.EMAIL, MessageChannel.BOTH):
        mail_users = filter_email(recipients, NotificationKind.MESSAGE)
        if mail_users:
            body = render_to_string(STAFF_MAIL_TEMPLATE, _context(message))
            records = mail_service.send_to_staff(
                subject=message.subject,
                body=body,
                recipients=[u.email for u in mail_users],
                template_name=STAFF_MAIL_TEMPLATE,
                payload={"scheduled_message_id": message.pk},
                actor=message.author,
            )
            sent_emails = {r.recipient_email for r in records if r.status == "SENT"}
            delivered.update(u.pk for u in mail_users if u.email in sent_emails)

    return len(delivered)
