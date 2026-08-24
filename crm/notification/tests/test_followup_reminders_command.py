from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from crm.notification.models import Notification
from crm.zetom.models import RequestMain, StepNote

User = get_user_model()


class FollowupRemindersCommandTests(TestCase):
    def setUp(self):
        self.assignee = User.objects.create_user(
            username="assignee_followup", password="x", is_active=True
        )
        self.owner = User.objects.create_user(
            username="owner_followup", password="x", is_active=True
        )
        self.author = User.objects.create_user(
            username="author_followup", password="x", is_active=True
        )

    def _request(self):
        return RequestMain.objects.create(
            phone="+48123123123",
            email="request@example.com",
            source="manual",
        )

    def test_creates_notification_for_due_note_and_marks_sent(self):
        req = self._request()
        req.assigned_to.add(self.assignee)
        note = StepNote.objects.create(
            author=self.author,
            target=req,
            kind=StepNote.Kind.REMINDER,
            text="Call client and confirm details",
            next_contact_at=timezone.now() - timedelta(hours=1),
        )

        call_command("create_followup_reminders")

        self.assertEqual(Notification.objects.count(), 1)
        n = Notification.objects.first()
        self.assertEqual(n.recipient, self.assignee)
        self.assertIn("next_contact_at", n.payload)
        note.refresh_from_db()
        self.assertIsNotNone(note.reminder_sent_at)

    def test_command_is_idempotent(self):
        req = self._request()
        req.assigned_to.add(self.assignee)
        StepNote.objects.create(
            author=self.author,
            target=req,
            kind=StepNote.Kind.REMINDER,
            text="Call client once",
            next_contact_at=timezone.now() - timedelta(minutes=10),
        )

        call_command("create_followup_reminders")
        call_command("create_followup_reminders")

        self.assertEqual(Notification.objects.count(), 1)

    def test_future_next_contact_does_not_create_notification(self):
        req = self._request()
        req.assigned_to.add(self.assignee)
        note = StepNote.objects.create(
            author=self.author,
            target=req,
            kind=StepNote.Kind.REMINDER,
            text="Future contact",
            next_contact_at=timezone.now() + timedelta(days=1),
        )

        call_command("create_followup_reminders")

        self.assertEqual(Notification.objects.count(), 0)
        note.refresh_from_db()
        self.assertIsNone(note.reminder_sent_at)

    def test_prefers_request_owner_over_assignee(self):
        req = self._request()
        req.assigned_to.add(self.assignee, self.owner)
        req.owners.add(self.owner)
        StepNote.objects.create(
            author=self.author,
            target=req,
            kind=StepNote.Kind.REMINDER,
            text="Owner must contact",
            next_contact_at=timezone.now() - timedelta(minutes=1),
        )

        call_command("create_followup_reminders")

        recipients = list(Notification.objects.values_list("recipient__username", flat=True))
        self.assertEqual(recipients, ["owner_followup"])

    def test_without_recipients_keeps_note_unsent(self):
        req = self._request()
        note = StepNote.objects.create(
            author=None,
            target=req,
            kind=StepNote.Kind.REMINDER,
            text="Nobody assigned yet",
            next_contact_at=timezone.now() - timedelta(minutes=1),
        )

        call_command("create_followup_reminders")

        self.assertEqual(Notification.objects.count(), 0)
        note.refresh_from_db()
        self.assertIsNone(note.reminder_sent_at)

    # claude
    def test_reminder_without_target_notifies_author(self):
        note = StepNote.objects.create(
            author=self.author,
            target=None,
            kind=StepNote.Kind.REMINDER,
            text="Call client back, no request yet",
            next_contact_at=timezone.now() - timedelta(hours=1),
        )

        call_command("create_followup_reminders")

        self.assertEqual(Notification.objects.count(), 1)
        n = Notification.objects.first()
        self.assertEqual(n.recipient, self.author)
        note.refresh_from_db()
        self.assertIsNotNone(note.reminder_sent_at)

    # claude
    def test_reminder_without_target_and_inactive_author_creates_nothing(self):
        self.author.is_active = False
        self.author.save(update_fields=["is_active"])
        note = StepNote.objects.create(
            author=self.author,
            target=None,
            kind=StepNote.Kind.REMINDER,
            text="Call client back, no request yet",
            next_contact_at=timezone.now() - timedelta(hours=1),
        )

        call_command("create_followup_reminders")

        self.assertEqual(Notification.objects.count(), 0)
        note.refresh_from_db()
        self.assertIsNone(note.reminder_sent_at)
