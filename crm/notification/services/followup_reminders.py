from django.db import transaction
from django.utils import timezone

from crm.notification.models import NotificationKind
from crm.notification.services import inapp_service
from crm.zetom.models import RequestMain, StepNote

TEMPLATE_NAME = "notification/inapp/staff/followup_due.txt"


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

        notifications = inapp_service.create_inapp(
            kind=NotificationKind.SYSTEM,
            template_name=TEMPLATE_NAME,
            payload={
                "target_label": str(target) if target is not None else "",
                "next_contact_at": timezone.localtime(locked.next_contact_at).strftime("%Y-%m-%d %H:%M"),
                "note_action": locked.action or "",
                "note_text": (locked.text or "")[:240],
                "author": locked.author.get_username() if locked.author_id else "system",
            },
            recipients=recipients,
            actor=locked.author,
            target=target,
        )
        if not notifications:
            return 0

        locked.reminder_sent_at = now
        locked.save(update_fields=["reminder_sent_at"])
        return len(notifications)


def _resolve_recipients(note: StepNote, target):
    if target is None:
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
