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
