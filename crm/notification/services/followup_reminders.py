from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from crm.notification.models import NotificationKind
from crm.notification.services import inapp_service, mail_service
from crm.notification.services.preferences import filter_email
from crm.zetom.models import RequestMain, StepNote

TEMPLATE_NAME = "notification/inapp/staff/followup_due.txt"
MAIL_TEMPLATE_NAME = "notification/mail/staff/followup_due.txt"


def process_due_followups(now=None):
    now = now or timezone.now()
    due_notes = StepNote.objects.filter(
        next_contact_at__isnull=False,
        next_contact_at__lte=now,
        reminder_sent_at__isnull=True,
    ).select_related("author", "target_content_type")

    created_notifications = 0
    processed_notes = 0

    for note in due_notes:
        created = _create_for_note(note, now)
        if created:
            processed_notes += 1
            created_notifications += created

    return processed_notes, created_notifications


def _create_for_note(note: StepNote, now):
    with transaction.atomic():
        locked = StepNote.objects.select_for_update().get(pk=note.pk)
        if locked.reminder_sent_at is not None:
            return 0

        target = locked.target
        # claude — "Komu przypomnieć: klient" — an email goes out at the set
        # time and the reminder closes itself (nothing left to do), landing
        # in the work log's history with its "sent" tag.
        if locked.notify == StepNote.Notify.CLIENT:
            sent = _email_client(locked, target)
            locked.reminder_sent_at = now
            locked.done_at = locked.done_at or now
            locked.save(update_fields=["reminder_sent_at", "done_at"])
            return sent

        recipients = _resolve_recipients(locked, target)
        if not recipients:
            return 0

        payload = {
            "target_label": str(target) if target is not None else "",
            "next_contact_at": timezone.localtime(locked.next_contact_at).strftime("%Y-%m-%d %H:%M"),
            "note_action": locked.action or "",
            "note_text": (locked.text or "")[:240],
            "author": locked.author.get_username() if locked.author_id else "system",
        }
        notifications = inapp_service.create_inapp(
            kind=NotificationKind.REMINDER,
            template_name=TEMPLATE_NAME,
            payload=payload,
            recipients=recipients,
            actor=locked.author,
            target=target,
        )
        # claude — email copy for whoever switched "Reminders by email" on.
        emailed = _email_reminder(recipients, payload, locked.author)

        # claude — stamped even when every recipient muted the inbox: a muted
        # reminder is a delivered one, otherwise it would retry every tick.
        locked.reminder_sent_at = now
        locked.save(update_fields=["reminder_sent_at"])
        return len(notifications) + emailed


def _resolve_recipients(note: StepNote, target):
    # claude — explicit addressee chosen in the work-log modal wins over the
    # default cascade below.
    addressed = _addressed_recipients(note)
    if addressed is not None:
        return addressed
    # claude — заметка без target (напоминание с карточки клиента) не имеет
    # ни владельцев, ни назначенных: единственный получатель — автор, если он активен.
    if target is None:
        if note.author_id and note.author.is_active:
            return [note.author]
        return []

    recipients = []
    main_request = _resolve_main_request(target)

    if main_request is not None:
        owners = list(main_request.owners.filter(is_active=True))
        if owners:
            recipients = owners

    if not recipients and hasattr(target, "assigned_to"):
        assignees = list(target.assigned_to.filter(is_active=True))
        if assignees:
            recipients = assignees

    if not recipients and main_request is not None:
        main_assignees = list(main_request.assigned_to.filter(is_active=True))
        if main_assignees:
            recipients = main_assignees

    if not recipients and note.author_id and note.author.is_active:
        recipients = [note.author]

    unique = []
    seen = set()
    for user in recipients:
        if user.pk not in seen:
            seen.add(user.pk)
            unique.append(user)
    return unique


def _resolve_main_request(target):
    if isinstance(target, RequestMain):
        return target
    if hasattr(target, "from_main"):
        return target.from_main
    return None


# claude
def _email_reminder(recipients, payload, actor):
    mail_users = filter_email(recipients, NotificationKind.REMINDER)
    if not mail_users:
        return 0
    rendered = render_to_string(MAIL_TEMPLATE_NAME, payload).lstrip()
    subject, _sep, body = rendered.partition("\n")
    records = mail_service.send_to_staff(
        subject=subject.strip(),
        body=body.lstrip("\n"),
        recipients=[u.email for u in mail_users],
        template_name=MAIL_TEMPLATE_NAME,
        payload=payload,
        actor=actor,
    )
    return len(records)


# claude
def _addressed_recipients(note):
    """Users a reminder was explicitly addressed to, or None when it uses the
    default cascade (notify empty)."""
    from django.contrib.auth import get_user_model
    from django.db.models import Q

    if note.notify == StepNote.Notify.SELF:
        return [note.author] if note.author_id and note.author.is_active else []
    if note.notify == StepNote.Notify.USERS:
        return list(note.notify_users.filter(is_active=True))
    if note.notify == StepNote.Notify.ROLES:
        roles = list(note.notify_roles or [])
        role_filter = Q(profile__role__code__in=roles)
        if "admin" in roles:
            role_filter |= Q(is_superuser=True)
        users = get_user_model().objects.filter(role_filter, is_active=True).distinct()
        return [u for u in users if u.pk != note.author_id]
    return None


# claude
CLIENT_MAIL_TEMPLATE = "notification/mail/client/message.txt"


def _email_client(note, target):
    from django.conf import settings
    from django.utils import translation

    author = note.author
    author_name = (author.get_full_name() or author.get_username()) if author else ""
    with translation.override(getattr(settings, "CLIENT_EMAIL_LANGUAGE", "pl")):
        subject = note.action or translation.gettext("Reminder: %(code)s") % {
            "code": str(target) if target is not None else "",
        }
        body = render_to_string(CLIENT_MAIL_TEMPLATE, {"body": note.text, "author": author_name})
    records = mail_service.send_to_client(
        to=note.client_email,
        subject=subject,
        body=body,
        template_name=CLIENT_MAIL_TEMPLATE,
        payload={"step_note_id": note.pk},
        actor=author,
    )
    return sum(1 for r in records if r.status == "SENT")
