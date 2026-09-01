# claude
"""Tests for the StepNote contact/reminder fields (Task 1) and the
backfill service (Task 2) and kind invariants (Task 3).

See .superpowers/sdd/2026-08-24-step-notes-unification/ for the briefs.
"""
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from crm.clients.models import Client
from crm.zetom.models import StepNote
from crm.zetom.services.step_notes import backfill_contact_kind


class StepNoteContactFieldsTest(TestCase):
    def test_can_create_reminder_without_text_or_target(self):
        note = StepNote.objects.create(
            kind=StepNote.Kind.REMINDER,
            next_contact_at=timezone.now() + timezone.timedelta(days=1),
        )
        note.refresh_from_db()
        self.assertEqual(note.kind, StepNote.Kind.REMINDER)
        self.assertEqual(note.text, "")
        self.assertIsNone(note.target_content_type_id)
        self.assertIsNone(note.target_object_id)

    def test_can_create_contact_with_channel_and_person(self):
        client = Client.objects.create(first_name="Anna", last_name="Kowalska")
        contacted_at = timezone.now()

        note = StepNote.objects.create(
            kind=StepNote.Kind.CONTACT,
            channel=StepNote.Channel.CALL,
            contacted_at=contacted_at,
            person=client,
        )
        note.refresh_from_db()

        self.assertEqual(note.kind, StepNote.Kind.CONTACT)
        self.assertEqual(note.channel, StepNote.Channel.CALL)
        self.assertEqual(note.contacted_at, contacted_at)
        self.assertEqual(note.person_id, client.pk)

    def test_contact_person_fallback_survives_without_person_fk(self):
        note = StepNote.objects.create(
            kind=StepNote.Kind.CONTACT,
            contacted_at=timezone.now(),
            person=None,
            contact_person="Anna z sekretariatu",
        )
        note.refresh_from_db()

        self.assertIsNone(note.person_id)
        self.assertEqual(note.contact_person, "Anna z sekretariatu")


class BackfillContactKindTest(TestCase):
    def test_backfill_sets_kind_and_contacted_at(self):
        # claude — до констрейнта Task 3 такие строки (kind=contact,
        # contacted_at=None) были обычным legacy-состоянием. После констрейнта
        # завести их напрямую нельзя — единственный kind, которому Meta
        # разрешает пустой contacted_at, это reminder. Используем его здесь
        # только чтобы получить пустой contacted_at и проверить, что backfill
        # находит такие строки и проставляет им kind=contact/contacted_at,
        # как и было бы для настоящих legacy-записей.
        blank_notes = [
            StepNote.objects.create(
                text="Note without contacted_at",
                kind=StepNote.Kind.REMINDER,
                next_contact_at=timezone.now() + timezone.timedelta(days=1),
            )
            for _ in range(3)
        ]
        already_set = timezone.now() - timezone.timedelta(days=5)
        filled_note = StepNote.objects.create(
            text="Already filled",
            contacted_at=already_set,
        )

        updated = backfill_contact_kind(StepNote)

        self.assertEqual(updated, 3)

        for note in blank_notes:
            note.refresh_from_db()
            self.assertEqual(note.kind, StepNote.Kind.CONTACT)
            self.assertEqual(note.contacted_at, note.created_at)

        filled_note.refresh_from_db()
        self.assertEqual(filled_note.contacted_at, already_set)


class StepNoteKindConstraintsTest(TestCase):
    def test_contact_without_contacted_at_is_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StepNote.objects.create(
                    kind=StepNote.Kind.CONTACT,
                    contacted_at=None,
                )

    def test_reminder_without_next_contact_at_is_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StepNote.objects.create(
                    kind=StepNote.Kind.REMINDER,
                    next_contact_at=None,
                )

    def test_clean_gives_friendly_error_before_db(self):
        note = StepNote(kind=StepNote.Kind.CONTACT, contacted_at=None)
        with self.assertRaises(ValidationError) as ctx:
            note.full_clean()
        self.assertIn("contacted_at", ctx.exception.message_dict)
