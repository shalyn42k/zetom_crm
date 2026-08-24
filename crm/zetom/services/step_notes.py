# claude
"""Service functions for StepNote, the unified contact/reminder log.

`backfill_contact_kind` is called by migration 0016 to bring legacy rows
(created before `kind`/`contacted_at` existed) in line with the invariants
Task 3 enforces via CheckConstraint. The logic lives here rather than
inline in the migration so it can be unit-tested directly; the migration
is a thin RunPython wrapper.
"""
from __future__ import annotations

from django.db.models import F


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
