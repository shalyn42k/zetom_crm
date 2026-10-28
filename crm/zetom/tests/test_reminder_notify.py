# claude
"""Dziennik kontaktów → "Komu przypomnieć": who a reminder may go to, who it
reaches at its time, and what the work log shows afterwards."""
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from crm.notification.models import (
    Notification, NotificationKind, NotificationPreference,
)
from crm.notification.services.followup_reminders import process_due_followups
from crm.users.models import Role
from crm.zetom.models import Oferta, RequestMain, StepNote

User = get_user_model()

DOC = {
    "first_name": "Jan", "last_name": "Kowalski", "phone": "+48501600300",
    "email": "jan@client.pl", "company_name": "Acme",
}


def make_user(username, role=None):
    user = User.objects.create_user(username=username, password="x", is_staff=True, email=f"{username}@zetom.pl")
    if role:
        user.profile.role = Role.objects.get(code=role)
        user.profile.save()
    return user


class ReminderNotifyTests(TestCase):
    def setUp(self):
        self.spec = make_user("spec")
        self.colleague = make_user("colleague")
        self.main = RequestMain.objects.create(**DOC)
        self.oferta = Oferta.objects.create(from_main=self.main, **DOC)
        for obj in (self.main, self.oferta):
            obj.assigned_to.add(self.spec, self.colleague)
        Notification.objects.all().delete()  # drop the assignment notifications
        self.client.force_login(self.spec)
        self.url = reverse("admin:zetom_oferta_step_note_create", args=[self.oferta.pk])
        self.soon = (timezone.localtime() + timezone.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")

    def _post(self, **data):
        payload = {"kind": "reminder", "next_contact_at": self.soon, "action": "Call back", **data}
        return self.client.post(self.url, payload)

    def _due(self):
        return process_due_followups(now=timezone.now() + timezone.timedelta(hours=2))

    def test_modal_offers_options_by_permission(self):
        response = self.client.get(reverse("admin:zetom_oferta_change", args=[self.oferta.pk]))
        options = [v for v, _label in response.context["step_notes_notify"]["options"]]
        self.assertEqual(options, ["self", "users", "client"])  # specialist: no roles
        self.assertContains(response, 'name="notify"')
        head = make_user("head", role="department_head")
        self.oferta.assigned_to.add(head)
        self.client.force_login(head)
        response = self.client.get(reverse("admin:zetom_oferta_change", args=[self.oferta.pk]))
        options = [v for v, _label in response.context["step_notes_notify"]["options"]]
        self.assertEqual(options, ["self", "users", "roles", "client"])

    def test_remind_colleague(self):
        self._post(notify="users", notify_users=[self.colleague.pk])
        note = StepNote.objects.get()
        self.assertEqual(note.notify, "users")
        self.assertEqual(note.notify_label, "colleague")
        self._due()
        rows = Notification.objects.filter(kind=NotificationKind.REMINDER)
        self.assertEqual([r.recipient for r in rows], [self.colleague])
        note.refresh_from_db()
        self.assertIsNotNone(note.reminder_sent_at)
        self.assertIsNone(note.done_at)  # still a task until ticked

    def test_remind_me_only(self):
        self._post(notify="self")
        self._due()
        rows = Notification.objects.filter(kind=NotificationKind.REMINDER)
        self.assertEqual([r.recipient for r in rows], [self.spec])

    def test_default_cascade_kept_for_old_rows(self):
        StepNote.objects.create(
            author=self.spec, target=self.oferta, kind=StepNote.Kind.REMINDER, text="old",
            next_contact_at=timezone.now() - timezone.timedelta(minutes=1),
        )
        process_due_followups()
        recipients = set(Notification.objects.values_list("recipient__username", flat=True))
        self.assertEqual(recipients, {"spec", "colleague"})  # assignees, as before

    def test_remind_client_by_email_closes_itself(self):
        self._post(notify="client", client_email="jan@client.pl", text="Dzień dobry, przypominamy.")
        note = StepNote.objects.get()
        self.assertEqual(note.notify_label, "client · jan@client.pl")
        self.assertEqual(len(mail.outbox), 0)  # not before its time
        self._due()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["jan@client.pl"])
        self.assertEqual(mail.outbox[0].subject, "Call back")
        self.assertIn("Dzień dobry, przypominamy.", mail.outbox[0].body)
        self.assertIn("Z poważaniem", mail.outbox[0].body)  # Polish signature from the tick
        note.refresh_from_db()
        self.assertIsNotNone(note.done_at)
        self.assertFalse(Notification.objects.exists())

    def test_client_address_can_be_typed(self):
        self._post(notify="client", client_email="biuro@inna-firma.pl", text="x")
        self.assertEqual(StepNote.objects.get().client_email, "biuro@inna-firma.pl")

    def test_invalid_client_address_rejected(self):
        self._post(notify="client", client_email="not-an-email", text="x")
        self.assertFalse(StepNote.objects.exists())

    def test_specialist_cannot_remind_a_role(self):
        response = self._post(notify="roles", notify_roles=["specialist"])
        self.assertEqual(response.status_code, 403)
        self.assertFalse(StepNote.objects.exists())

    def test_head_reminds_a_role(self):
        head = make_user("head", role="department_head")
        self.oferta.assigned_to.add(head)
        self.client.force_login(head)
        self._post(notify="roles", notify_roles=["specialist"])
        Notification.objects.all().delete()
        self._due()
        recipients = set(Notification.objects.filter(kind=NotificationKind.REMINDER).values_list("recipient__username", flat=True))
        self.assertEqual(recipients, {"spec", "colleague"})
        self.assertIn("role:", StepNote.objects.get().notify_label)

    def test_users_option_needs_someone(self):
        self._post(notify="users")
        self.assertFalse(StepNote.objects.exists())

    def test_contact_entries_never_carry_an_addressee(self):
        self.client.post(self.url, {
            "kind": "contact", "contacted_at": self.soon, "text": "talked",
            "notify": "client", "client_email": "jan@client.pl",
        })
        note = StepNote.objects.get()
        self.assertEqual(note.notify, "")
        self.assertEqual(note.client_email, "")

    def test_email_copy_respects_preference(self):
        NotificationPreference.objects.create(user=self.colleague, email_reminders=True)
        self._post(notify="users", notify_users=[self.colleague.pk])
        mail.outbox.clear()
        self._due()
        self.assertEqual([m.to for m in mail.outbox], [["colleague@zetom.pl"]])

    def test_timeline_shows_whom_and_sent(self):
        self._post(notify="users", notify_users=[self.colleague.pk])
        self._due()
        response = self.client.get(reverse("admin:zetom_oferta_change", args=[self.oferta.pk]))
        self.assertContains(response, "→ colleague")
        self.assertContains(response, "sn-tag--sent")
