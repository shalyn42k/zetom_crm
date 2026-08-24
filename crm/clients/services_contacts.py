# claude
"""Contact-history and reminders row-builders for the Person/Company cards
(Task 7 of the step-notes-unification plan).

Both cards used to build their "Historia kontaktów" rows straight from
`clients.ClientInteraction`; Task 6 migrated that data into `zetom.StepNote`
(kind=contact) and added a second kind (reminder) on the same model. This
module is the single place that turns StepNote rows into the two panels the
cards render — the row shape the templates consume (`data`, `kanal_label`,
`sotrudnik`, `kontakt_osoba`, `zaglowek`, `summary`) is unchanged from the
old ClientInteraction-based version (admin.py:523/724).

History = contact notes + *closed* reminders (spec §5.3: a closed reminder
leaves "Zaplanowane" but stays visible in the log). Reminders = open
(not-yet-done) reminders only.
"""
from __future__ import annotations

from django.db.models import Q, QuerySet
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from crm.zetom.models import Oferta, RequestMain, StepNote, Wniosek, Zlecenie

# claude — same PL words + msgid shape as admin.py's _PERSON_REQ_TYPE_LABEL /
# _zgloszenie_label (crm/clients/admin.py:45-64). Deliberately not imported
# from admin.py (that module will import the row-builders below — importing
# back would be circular); reusing the identical literal strings means
# makemessages sees the same msgid, so no new translations are needed.
_TARGET_TYPE_LABEL = {
    Oferta: _("Oferta"),
    Zlecenie: _("Zlecenie"),
    Wniosek: _("Wniosek"),
}


def _target_label(model: type, target) -> str:
    if model is RequestMain:
        return str(_("Zgłoszenie nr %(pk)s / %(year)s") % {
            "pk": target.pk, "year": target.created_at.year,
        })
    type_label = _TARGET_TYPE_LABEL.get(model)
    if type_label is None:
        return ""
    return str(_("%(type)s nr %(pk)s / %(year)s") % {
        "type": type_label, "pk": target.pk, "year": target.created_at.year,
    })


# claude — resolves every note's `target` (a nullable GenericForeignKey that
# can point at RequestMain, Oferta, Zlecenie, Wniosek, or nothing) into its
# `zaglowek` label without one query per note.
#
# select_related("target_content_type") on the caller's queryset already
# avoids a query for the ContentType row itself, but the GenericForeignKey's
# *target object* is not something select_related can follow — reading
# `note.target` directly would issue one query per note, and a company card
# with dozens of persons can have dozens of notes. Instead: group
# target_object_ids by model class (read off the already-loaded ContentType
# via .model_class(), which is a local lookup against the app registry, not
# a query), then fetch each group in a single .in_bulk() query. Worst case
# is one query per distinct target *type* present (at most 4: RequestMain/
# Oferta/Zlecenie/Wniosek), not one per row.
def _target_labels(notes: list[StepNote]) -> dict[int, str]:
    ids_by_model: dict[type, set[int]] = {}
    for note in notes:
        if note.target_content_type_id is None or note.target_object_id is None:
            continue
        model = note.target_content_type.model_class()
        ids_by_model.setdefault(model, set()).add(note.target_object_id)

    targets_by_model = {
        model: model.objects.filter(pk__in=ids).only("pk", "created_at").in_bulk()
        for model, ids in ids_by_model.items()
    }

    labels: dict[int, str] = {}
    for note in notes:
        if note.target_content_type_id is None or note.target_object_id is None:
            labels[note.pk] = ""
            continue
        model = note.target_content_type.model_class()
        target = targets_by_model.get(model, {}).get(note.target_object_id)
        labels[note.pk] = _target_label(model, target) if target is not None else ""
    return labels


def _history_row(note: StepNote, labels: dict[int, str]) -> dict:
    return {
        "data": note.contacted_at or note.created_at,
        "kanal_label": note.get_channel_display(),
        "sotrudnik": (
            note.author.get_full_name() or note.author.username
        ) if note.author_id else "",
        "kontakt_osoba": note.contact_person or (
            note.person.full_name() if note.person_id else ""
        ),
        "zaglowek": labels.get(note.pk, ""),
        "summary": note.text,
    }


# claude — contact notes OR closed reminders (done_at set); a reminder that
# is still open belongs to the "Zaplanowane" panel only.
_HISTORY_FILTER = Q(kind=StepNote.Kind.CONTACT) | Q(
    kind=StepNote.Kind.REMINDER, done_at__isnull=False,
)


def _history_notes(base_qs: QuerySet) -> list[StepNote]:
    # claude — closed reminders have no contacted_at (only next_contact_at),
    # so the sort falls back to created_at for them; Coalesce makes that
    # fallback part of the ORDER BY itself instead of a Python-side sort.
    return list(
        base_qs
        .filter(_HISTORY_FILTER)
        .select_related("author", "person", "target_content_type")
        .annotate(sort_at=Coalesce("contacted_at", "created_at"))
        .order_by("-sort_at")
    )


def contact_rows_for_person(client) -> list[dict]:
    notes = _history_notes(StepNote.objects.filter(person=client))
    labels = _target_labels(notes)
    return [_history_row(note, labels) for note in notes]


def contact_rows_for_company(company) -> list[dict]:
    notes = _history_notes(
        StepNote.objects.filter(person__company_links__company=company).distinct()
    )
    labels = _target_labels(notes)
    return [_history_row(note, labels) for note in notes]


def _reminder_row(note: StepNote, labels: dict[int, str], now) -> dict:
    row = _history_row(note, labels)
    row.update({
        "due_at": note.next_contact_at,
        "is_overdue": bool(note.next_contact_at and note.next_contact_at < now),
        "note_pk": note.pk,
    })
    return row


def _open_reminder_notes(base_qs: QuerySet) -> list[StepNote]:
    return list(
        base_qs
        .filter(kind=StepNote.Kind.REMINDER, done_at__isnull=True)
        .select_related("author", "person", "target_content_type")
        .order_by("next_contact_at")
    )


def reminder_rows_for_person(client) -> list[dict]:
    notes = _open_reminder_notes(StepNote.objects.filter(person=client))
    labels = _target_labels(notes)
    now = timezone.now()
    return [_reminder_row(note, labels, now) for note in notes]


def reminder_rows_for_company(company) -> list[dict]:
    notes = _open_reminder_notes(
        StepNote.objects.filter(person__company_links__company=company).distinct()
    )
    labels = _target_labels(notes)
    now = timezone.now()
    return [_reminder_row(note, labels, now) for note in notes]
