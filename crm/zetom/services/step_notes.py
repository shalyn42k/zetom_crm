# claude
"""Service functions for StepNote, the unified contact/reminder log.

`backfill_contact_kind` is called by migration 0016 to bring legacy rows
(created before `kind`/`contacted_at` existed) in line with the invariants
Task 3 enforces via CheckConstraint. The logic lives here rather than
inline in the migration so it can be unit-tested directly; the migration
is a thin RunPython wrapper.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from crm.zetom.models import StepNote


# claude
def create_step_note(
    *,
    author,
    kind,
    action="",
    text="",
    target=None,
    person=None,
    contact_person="",
    channel="",
    contacted_at=None,
    next_contact_at=None,
) -> StepNote:
    """Build, validate and save a StepNote. The single entry point for note
    creation — the admin action (Task 4) and the clients-side caller
    (Task 6) both go through this instead of `StepNote.objects.create`.

    `full_clean()` runs BEFORE `save()` so the kind/contacted_at/
    next_contact_at invariants (Task 3 CheckConstraints) surface as
    `ValidationError` with a field-level message, not as an `IntegrityError`
    from the database.
    """
    note = StepNote(
        author=author,
        kind=kind,
        action=action,
        text=text,
        person=person,
        contact_person=contact_person,
        channel=channel,
        contacted_at=contacted_at,
        next_contact_at=next_contact_at,
    )
    if target is not None:
        note.target = target
    note.full_clean()
    note.save()
    return note


# claude
def mark_reminder_done(note: StepNote, user) -> StepNote:
    """Mark a reminder note as done. Idempotent — a second call does not
    move an already-set `done_at`. Rejects notes whose kind isn't reminder.

    `user` is accepted for signature symmetry with `create_step_note` (who
    performed the action); nothing currently reads it, there's no
    `done_by` field yet.
    """
    if note.kind != StepNote.Kind.REMINDER:
        raise ValidationError(_("Only reminders can be marked done."))
    if note.done_at is None:
        note.done_at = timezone.now()
        note.full_clean()
        note.save(update_fields=["done_at"])
    return note


def backfill_contact_kind(step_note_model) -> int:
    """Set kind=contact and contacted_at=created_at on rows missing contacted_at.

    `step_note_model` is passed in rather than imported so the migration can
    hand over the historical model version via `apps.get_model`. That
    historical model is reconstructed from migration state and does not
    carry the `Kind` nested class (only fields survive), so the "contact"
    value is used literally here — it must stay in sync with
    `StepNote.Kind.CONTACT` in crm/zetom/models.py.
    Returns the number of rows updated.
    """
    return step_note_model.objects.filter(contacted_at__isnull=True).update(
        kind="contact",
        contacted_at=F("created_at"),
    )
