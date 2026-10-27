# claude
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.utils import timezone

from crm.notification.models import (
    EmailNotification, MessageAudience, MessageChannel, MessageStatus,
    Notification, NotificationKind, NotificationPreference, ScheduledMessage,
)
from crm.notification.services import preferences
from crm.notification.services.scheduled_messages import (
    cancel_message, deliver, process_due_messages, schedule_message,
)
from crm.users.models import Role
from crm.zetom.models import Oferta

User = get_user_model()

DOC = {
    "first_name": "Jan", "last_name": "Kowalski",
    "phone": "+48501600300", "email": "jan@client.pl", "company_name": "Zetom",
}


def make_user(username, role=None, **extra):
    user = User.objects.create_user(username=username, password="x", is_staff=True, email=f"{username}@zetom.pl", **extra)
    if role:
        user.profile.role = Role.objects.get(code=role)
        user.profile.save()
    return user


class ScheduleMessageTests(TestCase):
    def setUp(self):
        self.author = make_user("author", role="department_head")
        self.doc = Oferta.objects.create(**DOC)

    def test_client_message_sent_now_by_email(self):
        msg = schedule_message(
            author=self.author, audience=MessageAudience.CLIENT, subject="Reminder",
            body="Please reply", client_email="jan@client.pl", target=self.doc,
            channel=MessageChannel.INAPP,  # ignored for clients: email only
        )
        self.assertEqual(msg.status, MessageStatus.SENT)
        self.assertEqual(msg.channel, MessageChannel.EMAIL)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["jan@client.pl"])
        self.assertIn("Please reply", mail.outbox[0].body)
        self.assertEqual(EmailNotification.objects.filter(recipient_email="jan@client.pl").count(), 1)

    def test_client_message_requires_email(self):
        with self.assertRaises(ValueError):
            schedule_message(author=self.author, audience=MessageAudience.CLIENT, subject="s", body="b")

    def test_future_message_waits_for_its_time(self):
        later = timezone.now() + timezone.timedelta(hours=2)
        colleague = make_user("colleague")
        msg = schedule_message(
            author=self.author, audience=MessageAudience.USERS, subject="Follow up",
            body="Call them", users=[colleague], send_at=later, target=self.doc,
        )
        self.assertEqual(msg.status, MessageStatus.PENDING)
        self.assertEqual(process_due_messages(), 0)
        self.assertFalse(Notification.objects.filter(recipient=colleague).exists())

        self.assertEqual(process_due_messages(now=later + timezone.timedelta(minutes=1)), 1)
        msg.refresh_from_db()
        self.assertEqual(msg.status, MessageStatus.SENT)
        note = Notification.objects.get(recipient=colleague)
        self.assertEqual(note.kind, NotificationKind.MESSAGE)
        self.assertEqual(note.target, self.doc)

    def test_role_broadcast_reaches_role_and_skips_author(self):
        spec_a = make_user("spec_a")  # specialist is the default role
        spec_b = make_user("spec_b")
        outsider = make_user("auditor_user", role="auditor")
        make_user("inactive_spec", is_active=False)
        msg = schedule_message(
            author=self.author, audience=MessageAudience.ROLES, subject="All hands",
            body="Meeting at 10", roles=["specialist", "department_head"],
        )
        recipients = set(Notification.objects.filter(kind=NotificationKind.MESSAGE).values_list("recipient__username", flat=True))
        self.assertEqual(recipients, {spec_a.username, spec_b.username})
        self.assertNotIn(outsider.username, recipients)
        self.assertEqual(msg.recipients_count, 2)

    def test_both_channels_respect_preferences(self):
        muted_inbox = make_user("muted_inbox")
        no_mail = make_user("no_mail")
        NotificationPreference.objects.create(user=muted_inbox, inapp_messages=False)
        NotificationPreference.objects.create(user=no_mail, email_messages=False)
        schedule_message(
            author=self.author, audience=MessageAudience.USERS, channel=MessageChannel.BOTH,
            subject="Hi", body="Text", users=[muted_inbox, no_mail],
        )
        self.assertEqual(list(Notification.objects.values_list("recipient__username", flat=True)), ["no_mail"])
        self.assertEqual([m.to for m in mail.outbox], [["muted_inbox@zetom.pl"]])

    def test_nobody_accepts_marks_failed(self):
        muted = make_user("muted")
        NotificationPreference.objects.create(user=muted, inapp_messages=False)
        msg = schedule_message(
            author=self.author, audience=MessageAudience.USERS, subject="s", body="b", users=[muted],
        )
        self.assertEqual(msg.status, MessageStatus.FAILED)

    def test_cancelled_message_is_never_sent(self):
        colleague = make_user("colleague")
        msg = schedule_message(
            author=self.author, audience=MessageAudience.USERS, subject="s", body="b",
            users=[colleague], send_at=timezone.now() + timezone.timedelta(hours=1),
        )
        self.assertTrue(cancel_message(msg))
        self.assertFalse(cancel_message(msg))
        process_due_messages(now=timezone.now() + timezone.timedelta(hours=2))
        msg.refresh_from_db()
        self.assertEqual(msg.status, MessageStatus.CANCELLED)
        self.assertFalse(Notification.objects.exists())

    def test_deliver_is_idempotent(self):
        colleague = make_user("colleague")
        msg = schedule_message(
            author=self.author, audience=MessageAudience.USERS, subject="s", body="b",
            users=[colleague], send_at=timezone.now() + timezone.timedelta(hours=1),
        )
        self.assertEqual(deliver(msg), 1)
        self.assertEqual(deliver(msg), 0)
        self.assertEqual(Notification.objects.count(), 1)


class PreferenceFilterTests(TestCase):
    def setUp(self):
        self.a = make_user("a")
        self.b = make_user("b")

    def test_defaults_without_rows(self):
        self.assertEqual(preferences.filter_inapp([self.a, self.b], NotificationKind.ASSIGNMENT), [self.a, self.b])
        # email reminders are opt-in
        self.assertEqual(preferences.filter_email([self.a], NotificationKind.REMINDER), [])
        self.assertEqual(preferences.filter_email([self.a], NotificationKind.MESSAGE), [self.a])

    def test_muted_kind_is_dropped(self):
        NotificationPreference.objects.create(user=self.a, inapp_status_change=False)
        self.assertEqual(preferences.filter_inapp([self.a, self.b], NotificationKind.STATUS_CHANGE), [self.b])

    def test_review_requests_cannot_be_muted(self):
        NotificationPreference.objects.create(
            user=self.a, **{f: False for f in preferences.PREFERENCE_FIELDS},
        )
        self.assertEqual(preferences.filter_inapp([self.a], NotificationKind.REVIEW_REQUEST), [self.a])

    def test_create_inapp_respects_preferences(self):
        from crm.notification.services.inapp_service import create_inapp

        NotificationPreference.objects.create(user=self.a, inapp_assignment=False)
        rows = create_inapp(
            kind=NotificationKind.ASSIGNMENT, template_name="x.txt", payload={}, recipients=[self.a, self.b],
        )
        self.assertEqual([r.recipient for r in rows], [self.b])

    def test_update_preferences_round_trip(self):
        preferences.update_preferences(self.a, {"email_reminders": True})
        pref = preferences.get_preferences(self.a)
        self.assertTrue(pref.email_reminders)
        self.assertFalse(pref.inapp_assignment)  # unchecked box = off
        self.assertEqual(ScheduledMessage.objects.count(), 0)


# claude
class AssignmentNotificationTests(TestCase):
    def test_added_user_gets_notified_but_not_the_actor(self):
        from crm.zetom.models import RequestMain

        actor = make_user("actor", role="department_head")
        spec = make_user("spec")
        req = RequestMain.objects.create(**DOC)
        req._actor = actor
        req.assigned_to.add(spec, actor)
        rows = Notification.objects.filter(kind=NotificationKind.ASSIGNMENT)
        self.assertEqual([r.recipient for r in rows], [spec])
        self.assertEqual(rows[0].target, req)

    def test_muted_assignment(self):
        from crm.zetom.models import RequestMain

        spec = make_user("spec")
        NotificationPreference.objects.create(user=spec, inapp_assignment=False)
        RequestMain.objects.create(**DOC).assigned_to.add(spec)
        self.assertFalse(Notification.objects.filter(kind=NotificationKind.ASSIGNMENT).exists())


# claude
class FollowupEmailCopyTests(TestCase):
    def test_reminder_email_only_for_opted_in(self):
        from crm.notification.services.followup_reminders import (
            process_due_followups,
        )
        from crm.zetom.models import RequestMain, StepNote

        opted = make_user("opted")
        plain = make_user("plain")
        NotificationPreference.objects.create(user=opted, email_reminders=True)
        req = RequestMain.objects.create(**DOC)
        req.assigned_to.add(opted, plain)
        mail.outbox.clear()
        StepNote.objects.create(
            author=opted, target=req, kind=StepNote.Kind.REMINDER, text="Call",
            next_contact_at=timezone.now() - timezone.timedelta(minutes=5),
        )
        process_due_followups()
        self.assertEqual([m.to for m in mail.outbox], [["opted@zetom.pl"]])
        self.assertEqual(
            set(Notification.objects.filter(kind=NotificationKind.REMINDER).values_list("recipient__username", flat=True)),
            {"opted", "plain"},
        )


# claude
class PlainTextEscapingTests(TestCase):
    def test_quotes_survive_in_email_and_inbox(self):
        from crm.notification.utils import render_notification

        author = make_user("author", role="department_head")
        colleague = make_user("colleague")
        text = 'Don\'t forget the "A&B" offer'
        schedule_message(
            author=author, audience=MessageAudience.CLIENT, subject="s", body=text,
            client_email="jan@client.pl",
        )
        self.assertIn(text, mail.outbox[0].body)
        schedule_message(author=author, audience=MessageAudience.USERS, subject="s", body=text, users=[colleague])
        _title, body = render_notification(Notification.objects.get(recipient=colleague))
        self.assertIn(text, body)


# claude
class SystemTemplatesEscapingTests(TestCase):
    def test_company_ampersand_not_double_escaped(self):
        from crm.notification.utils import render_notification
        from crm.zetom.models import RequestMain

        spec = make_user("spec")
        req = RequestMain.objects.create(**{**DOC, "company_name": "A&B"})
        req.assigned_to.add(spec)
        title, _body = render_notification(Notification.objects.get(kind=NotificationKind.ASSIGNMENT))
        self.assertIn("A&B", title)
        self.assertNotIn("&amp;", title)
