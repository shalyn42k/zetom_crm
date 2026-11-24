# claude
"""Tests for Task 4: create_step_note / mark_reminder_done service, and the
admin action that now routes through it.

See .superpowers/sdd/2026-08-24-step-notes-unification/task-4-brief.md.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from crm.clients.models import Client
from crm.zetom.models import RequestMain, StepNote
from crm.zetom.services.step_notes import create_step_note, mark_reminder_done

BASE_MAIN_DATA = {
    "first_name": "Jan",
    "last_name": "Kowalski",
    "phone": "+48500100200",
    "email": "jan@example.com",
    "company_name": "Zetom",
}


class CreateStepNoteTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_superuser(
            username="admin", email="a@a.com", password="x"
        )
        cls.main = RequestMain.objects.create(**BASE_MAIN_DATA)

    def test_create_contact_note_persists_all_fields(self):
        client_person = Client.objects.create(first_name="Anna", last_name="Kowalska")
        contacted_at = timezone.now()

        note = create_step_note(
            author=self.user,
            kind=StepNote.Kind.CONTACT,
            action="Zadzwoniono",
            text="Rozmowa o ofercie",
            target=self.main,
            person=client_person,
            channel=StepNote.Channel.CALL,
            contacted_at=contacted_at,
        )

        note.refresh_from_db()
        self.assertEqual(note.kind, StepNote.Kind.CONTACT)
        self.assertEqual(note.action, "Zadzwoniono")
        self.assertEqual(note.text, "Rozmowa o ofercie")
        self.assertEqual(note.target_object_id, self.main.pk)
        self.assertEqual(note.person_id, client_person.pk)
        self.assertEqual(note.channel, StepNote.Channel.CALL)
        self.assertEqual(note.contacted_at, contacted_at)
        self.assertEqual(note.author_id, self.user.pk)

    def test_create_reminder_without_target_is_allowed(self):
        next_contact_at = timezone.now() + timezone.timedelta(days=2)

        note = create_step_note(
            author=self.user,
            kind=StepNote.Kind.REMINDER,
            next_contact_at=next_contact_at,
        )

        note.refresh_from_db()
        self.assertEqual(note.kind, StepNote.Kind.REMINDER)
        self.assertIsNone(note.target_content_type_id)
        self.assertIsNone(note.target_object_id)
        self.assertEqual(note.next_contact_at, next_contact_at)

    def test_create_rejects_contact_without_contacted_at(self):
        with self.assertRaises(ValidationError):
            create_step_note(
                author=self.user,
                kind=StepNote.Kind.CONTACT,
                target=self.main,
            )
        self.assertEqual(StepNote.objects.count(), 0)


class MarkReminderDoneTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_superuser(
            username="admin2", email="b@b.com", password="x"
        )

    def test_mark_reminder_done_sets_done_at(self):
        note = StepNote.objects.create(
            kind=StepNote.Kind.REMINDER,
            next_contact_at=timezone.now() + timezone.timedelta(days=1),
        )
        self.assertIsNone(note.done_at)

        result = mark_reminder_done(note, self.user)

        self.assertIsNotNone(result.done_at)
        note.refresh_from_db()
        self.assertIsNotNone(note.done_at)

    def test_mark_reminder_done_is_idempotent(self):
        note = StepNote.objects.create(
            kind=StepNote.Kind.REMINDER,
            next_contact_at=timezone.now() + timezone.timedelta(days=1),
        )
        first = mark_reminder_done(note, self.user)
        first_done_at = first.done_at

        second = mark_reminder_done(note, self.user)

        self.assertEqual(second.done_at, first_done_at)

    def test_mark_reminder_done_rejects_contact_note(self):
        note = StepNote.objects.create(
            kind=StepNote.Kind.CONTACT,
            contacted_at=timezone.now(),
        )
        with self.assertRaises(ValidationError):
            mark_reminder_done(note, self.user)


@patch("crm.zetom.admin.base.user_has_perm")
class StepNoteCreateActionHttpTest(TestCase):
    """Regression test: the admin "add note" button used to raise
    IntegrityError (StepNote.objects.create with no kind/contacted_at).
    This drives the real HTTP path through the admin action end to end.

    # claude — user_has_perm is patched at its point of use (base.py), so
    # every test in this class fully controls has_change_permission's
    # answer; the real implementation (superuser bypass and all) never
    # runs. The superuser account exists only to satisfy
    # visible_requests_for (crm/zetom/services/visibility.py), which is an
    # unrelated specialist-visibility filter — it is not what gates access
    # here. Do not rely on `side_effect=lambda ...: perm == "edit_requests"`
    # to prove denial: has_change_permission only ever calls the mock with
    # "edit_requests", so that lambda can never return False. The negative
    # case below uses `return_value=False` instead, matching the pattern in
    # test_admin.py:240 (test_mail_freeform_returns_403_without_...).
    """

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_superuser(
            username="admin3", email="c@c.com", password="x"
        )
        cls.main = RequestMain.objects.create(**BASE_MAIN_DATA)

    def setUp(self):
        self.client.force_login(self.user)

    def test_step_note_create_action_creates_note_via_admin_post(self, perm_mock):
        perm_mock.return_value = True
        url = reverse("admin:zetom_requestmain_step_note_create", args=[self.main.pk])

        response = self.client.post(url, {
            "kind": StepNote.Kind.CONTACT,
            "channel": StepNote.Channel.CALL,
            "action": "Zadzwoniono",
            "text": "Rozmowa",
            "contacted_at": "2026-08-24T12:00",
        })

        self.assertEqual(response.status_code, 302)
        content_type = ContentType.objects.get_for_model(RequestMain)
        note = StepNote.objects.get(
            target_content_type=content_type, target_object_id=self.main.pk
        )
        self.assertEqual(note.kind, StepNote.Kind.CONTACT)
        self.assertIsNotNone(note.contacted_at)
        self.assertEqual(note.channel, StepNote.Channel.CALL)
        self.assertEqual(note.author_id, self.user.pk)

    def test_step_note_create_action_returns_403_without_edit_requests_permission(
        self, perm_mock
    ):
        perm_mock.return_value = False
        url = reverse("admin:zetom_requestmain_step_note_create", args=[self.main.pk])

        response = self.client.post(url, {
            "kind": StepNote.Kind.CONTACT,
            "channel": StepNote.Channel.CALL,
            "action": "Zadzwoniono",
            "text": "Rozmowa",
            "contacted_at": "2026-08-24T12:00",
        })

        self.assertEqual(response.status_code, 403)
        self.assertEqual(StepNote.objects.count(), 0)

    def test_step_note_create_action_redirects_with_error_on_invalid_payload(
        self, perm_mock
    ):
        # claude — kind=contact without contacted_at trips the model-level
        # ValidationError (StepNote.clean(), Task 3 invariant). This is the
        # exact failure mode Task 4 exists to prevent: full_clean() inside
        # create_step_note() must catch it before the DB does, and the admin
        # action must turn it into messages.error + redirect, not a 500.
        perm_mock.return_value = True
        url = reverse("admin:zetom_requestmain_step_note_create", args=[self.main.pk])

        response = self.client.post(url, {
            "kind": StepNote.Kind.CONTACT,
            "action": "Zadzwoniono",
            "text": "Rozmowa",
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            reverse("admin:zetom_requestmain_change", args=[self.main.pk]),
        )
        self.assertEqual(StepNote.objects.count(), 0)
        error_messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(
            any("Could not add note" in message for message in error_messages),
            error_messages,
        )
