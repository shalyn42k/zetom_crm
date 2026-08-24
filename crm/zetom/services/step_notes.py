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


# claude
def migrate_client_interactions(interaction_model, step_note_model, content_type_model) -> int:
    """Copy every `clients.ClientInteraction` row into `zetom.StepNote` as
    kind="contact". Used by migration 0010 (clients app), which hands over
    historical model versions via `apps.get_model`; the historical models
    don't expose `StepNote.Kind`, so "contact" is used literally here — same
    reasoning as `backfill_contact_kind` above.

    `target` is a GenericForeignKey and can't be assigned on a historical
    model, so `target_content_type`/`target_object_id` are set directly.
    `content_type_model` is passed in for the same reason as the other two
    models: the migration needs the historical `ContentType`.

    `created_at` is `auto_now_add` on StepNote, so migrated rows get "now"
    rather than the original `ClientInteraction.created_at` — accepted,
    panels sort by `contacted_at`, which IS copied faithfully.

    Returns the number of StepNote rows created.
    """
    request_content_type = content_type_model.objects.get_for_model(
        interaction_model._meta.get_field("request").related_model
    )

    # claude — order_by("contacted_at") overrides ClientInteraction.Meta.ordering
    # (-contacted_at). Without it, rows are read newest-first, and since
    # StepNote.created_at is auto_now_add (stamped in insertion order), the
    # two orderings would disagree — created_at would run opposite to
    # contacted_at instead of merely being a different, unrelated timestamp.
    notes = []
    for interaction in interaction_model.objects.all().order_by("contacted_at"):
        notes.append(
            step_note_model(
                person_id=interaction.client_id,
                target_content_type=request_content_type if interaction.request_id else None,
                target_object_id=interaction.request_id,
                channel=interaction.channel,
                text=interaction.summary,
                author_id=interaction.contacted_by_id,
                contact_person=interaction.contact_person,
                contacted_at=interaction.contacted_at,
                kind="contact",
            )
        )
    # claude — explicit batch_size: Postgres doesn't override Django's default
    # bulk_batch_size, so without this the whole table becomes one INSERT.
    # Under psycopg3 (Django 5.2 supports it), 14 columns against the
    # 65535-parameter cap crashes above ~4,600 rows. Production row count is
    # unknown from this environment, so this must be safe unconditionally.
    step_note_model.objects.bulk_create(notes, batch_size=500)
    return len(notes)


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
