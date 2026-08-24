# claude
"""Tests for Task 6: migrate_client_interactions, the helper that copies
`clients.ClientInteraction` rows into `zetom.StepNote` (kind=contact).

See .superpowers/sdd/2026-08-24-step-notes-unification/task-6-brief.md.

These exercise `migrate_client_interactions` directly against the live
(non-historical) models — that is enough to prove the mapping is correct.
The migration itself (0010_migrate_interactions_to_step_notes.py) is a thin
RunPython wrapper that hands the historical models to this same helper, the
same pattern migration 0016 uses for `backfill_contact_kind`.

No production database is reachable from this environment, so the test
matrix here is deliberately wider than the brief's own cases — see the
task-6 report for the full list and for shapes still NOT covered.
"""
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.utils import timezone

from crm.clients.models import Client, ClientInteraction
from crm.zetom.models import RequestMain, StepNote
from crm.zetom.services.step_notes import migrate_client_interactions

User = get_user_model()


# claude
class MigrateClientInteractionsTest(TestCase):
    def setUp(self):
        self.person = Client.objects.create(first_name="Jan", last_name="Kowalski")
        self.user = User.objects.create_user("staff", "s@s.pl", "pass12345")
        self.main = RequestMain.objects.create()
        self.now = timezone.now()

    def test_migrates_every_interaction_field_for_field(self):
        with_request = ClientInteraction.objects.create(
            client=self.person,
            request=self.main,
            channel=ClientInteraction.Channel.CALL,
            summary="Rozmowa o ofercie",
            contacted_by=self.user,
            contact_person="Anna Nowak",
            contacted_at=self.now,
        )
        without_request = ClientInteraction.objects.create(
            client=self.person,
            request=None,
            channel=ClientInteraction.Channel.EMAIL,
            summary="Wysłano ofertę mailem",
            contacted_by=self.user,
            contact_person="Piotr Zieliński",
            contacted_at=self.now,
        )
        empty_contact_person = ClientInteraction.objects.create(
            client=self.person,
            request=None,
            channel=ClientInteraction.Channel.CHAT,
            summary="Krótka rozmowa na czacie",
            contacted_by=self.user,
            contact_person="",
            contacted_at=self.now,
        )

        migrated = migrate_client_interactions(
            ClientInteraction, StepNote, ContentType
        )

        self.assertEqual(migrated, 3)
        self.assertEqual(StepNote.objects.filter(kind="contact").count(), 3)

        content_type = ContentType.objects.get_for_model(RequestMain)

        note = StepNote.objects.get(contact_person="Anna Nowak")
        self.assertEqual(note.person_id, with_request.client_id)
        self.assertEqual(note.channel, with_request.channel)
        self.assertEqual(note.text, with_request.summary)
        self.assertEqual(note.author_id, with_request.contacted_by_id)
        self.assertEqual(note.contact_person, with_request.contact_person)
        self.assertEqual(note.contacted_at, with_request.contacted_at)
        self.assertEqual(note.kind, "contact")
        self.assertEqual(note.target_content_type_id, content_type.id)
        self.assertEqual(note.target_object_id, with_request.request_id)
        self.assertEqual(note.target, self.main)

        note2 = StepNote.objects.get(contact_person="Piotr Zieliński")
        self.assertEqual(note2.person_id, without_request.client_id)
        self.assertEqual(note2.channel, without_request.channel)
        self.assertEqual(note2.text, without_request.summary)
        self.assertEqual(note2.author_id, without_request.contacted_by_id)
        self.assertEqual(note2.contact_person, without_request.contact_person)
        self.assertEqual(note2.contacted_at, without_request.contacted_at)
        self.assertEqual(note2.kind, "contact")
        self.assertIsNone(note2.target_content_type_id)
        self.assertIsNone(note2.target_object_id)
        self.assertIsNone(note2.target)

        note3 = StepNote.objects.get(text=empty_contact_person.summary)
        self.assertEqual(note3.contact_person, "")
        self.assertEqual(note3.person_id, empty_contact_person.client_id)
        self.assertEqual(note3.contacted_at, empty_contact_person.contacted_at)

    def test_migrates_interaction_without_author(self):
        interaction = ClientInteraction.objects.create(
            client=self.person,
            request=None,
            channel=ClientInteraction.Channel.MEETING,
            summary="Spotkanie bez przypisanego autora",
            contacted_by=None,
            contact_person="",
            contacted_at=self.now,
        )

        migrated = migrate_client_interactions(
            ClientInteraction, StepNote, ContentType
        )

        self.assertEqual(migrated, 1)
        note = StepNote.objects.get(kind="contact")
        self.assertIsNone(note.author)
        self.assertIsNone(note.author_id)
        self.assertEqual(note.text, interaction.summary)

    # claude — production ClientInteraction rows can have contacted_by NULL
    # (the FK is nullable): covered above by test_migrates_interaction_without_author,
    # duplicated here as an explicit field-by-field check per the controller's
    # widened matrix requirement.
    def test_author_is_none_when_contacted_by_is_null(self):
        ClientInteraction.objects.create(
            client=self.person,
            request=None,
            channel=ClientInteraction.Channel.OTHER,
            summary="Bez autora",
            contacted_by=None,
            contact_person="",
            contacted_at=self.now,
        )

        migrate_client_interactions(ClientInteraction, StepNote, ContentType)

        note = StepNote.objects.get(kind="contact")
        self.assertIsNone(note.author)

    # claude — request NULL must leave BOTH target fields None, not just one.
    def test_target_fields_are_both_none_when_request_is_null(self):
        ClientInteraction.objects.create(
            client=self.person,
            request=None,
            channel=ClientInteraction.Channel.CALL,
            summary="Bez zapytania",
            contacted_by=self.user,
            contact_person="",
            contacted_at=self.now,
        )

        migrate_client_interactions(ClientInteraction, StepNote, ContentType)

        note = StepNote.objects.get(kind="contact")
        self.assertIsNone(note.target_content_type_id)
        self.assertIsNone(note.target_object_id)

    # claude — empty string contact_person must stay "", not become None.
    def test_empty_contact_person_is_preserved_not_nulled(self):
        ClientInteraction.objects.create(
            client=self.person,
            request=None,
            channel=ClientInteraction.Channel.CALL,
            summary="Puste contact_person",
            contacted_by=self.user,
            contact_person="",
            contacted_at=self.now,
        )

        migrate_client_interactions(ClientInteraction, StepNote, ContentType)

        note = StepNote.objects.get(kind="contact")
        self.assertEqual(note.contact_person, "")
        self.assertIsNotNone(note.contact_person)

    # claude — non-ASCII summary (Polish diacritics) must survive byte-identical.
    def test_non_ascii_summary_survives_byte_identical(self):
        text = "Rozmowa o wdrożeniu — ąćęłńóśźż ĄĆĘŁŃÓŚŹŻ"
        ClientInteraction.objects.create(
            client=self.person,
            request=None,
            channel=ClientInteraction.Channel.CALL,
            summary=text,
            contacted_by=self.user,
            contact_person="",
            contacted_at=self.now,
        )

        migrate_client_interactions(ClientInteraction, StepNote, ContentType)

        note = StepNote.objects.get(kind="contact")
        self.assertEqual(note.text, text)

    # claude — exact count parity between source and migrated rows.
    def test_exact_count_parity(self):
        for i in range(5):
            ClientInteraction.objects.create(
                client=self.person,
                request=None,
                channel=ClientInteraction.Channel.CALL,
                summary=f"Rozmowa {i}",
                contacted_by=self.user,
                contact_person="",
                contacted_at=self.now,
            )

        original_count = ClientInteraction.objects.count()
        migrated = migrate_client_interactions(ClientInteraction, StepNote, ContentType)

        self.assertEqual(original_count, 5)
        self.assertEqual(migrated, original_count)
        self.assertEqual(StepNote.objects.filter(kind="contact").count(), original_count)
