# claude
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from crm.notification.models import (
    MessageAudience, MessageStatus, Notification, NotificationPreference,
    ScheduledMessage,
)
from crm.notification.services.scheduled_messages import schedule_message
from crm.notification.tests.test_scheduled_messages import DOC, make_user
from crm.zetom.models import Oferta


class ComposeViewTests(TestCase):
    def setUp(self):
        self.spec = make_user("spec")
        self.doc = Oferta.objects.create(**DOC)
        self.doc.assigned_to.add(self.spec)
        self.client.force_login(self.spec)
        self.url = reverse("notification:message_compose")

    def _post(self, **data):
        payload = {"target": f"oferta:{self.doc.pk}", "subject": "Hello", "body": "Text", **data}
        return self.client.post(self.url, payload)

    def test_specialist_emails_the_client(self):
        response = self._post(audience=MessageAudience.CLIENT, client_email="jan@client.pl")
        self.assertRedirects(
            response, reverse("admin:zetom_oferta_change", args=[self.doc.pk]) + "#messages",
            fetch_redirect_response=False,
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(ScheduledMessage.objects.get().status, MessageStatus.SENT)

    def test_client_email_must_belong_to_the_document(self):
        self._post(audience=MessageAudience.CLIENT, client_email="attacker@evil.example")
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(ScheduledMessage.objects.exists())

    def test_specialist_cannot_broadcast_to_roles(self):
        response = self._post(audience=MessageAudience.ROLES, roles=["specialist"])
        self.assertEqual(response.status_code, 403)
        self.assertFalse(ScheduledMessage.objects.exists())

    def test_specialist_schedules_a_reminder_for_a_colleague(self):
        colleague = make_user("colleague")
        when = (timezone.localtime() + timezone.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        self._post(audience=MessageAudience.USERS, users=[colleague.pk], send_at=when)
        msg = ScheduledMessage.objects.get()
        self.assertEqual(msg.status, MessageStatus.PENDING)
        self.assertEqual(list(msg.recipient_users.all()), [colleague])
        self.assertFalse(Notification.objects.exists())

    def test_past_send_at_is_rejected(self):
        colleague = make_user("colleague")
        past = (timezone.localtime() - timezone.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        self._post(audience=MessageAudience.USERS, users=[colleague.pk], send_at=past)
        self.assertFalse(ScheduledMessage.objects.exists())

    def test_invisible_document_is_404(self):
        other = Oferta.objects.create(**DOC)
        stranger = make_user("stranger")
        other.assigned_to.add(stranger)
        response = self.client.post(self.url, {
            "target": f"oferta:{other.pk}", "audience": MessageAudience.CLIENT,
            "client_email": "jan@client.pl", "subject": "s", "body": "b",
        })
        self.assertEqual(response.status_code, 404)

    def test_bad_target_is_404(self):
        response = self.client.post(self.url, {"target": "user:1", "audience": "CLIENT", "subject": "s", "body": "b"})
        self.assertEqual(response.status_code, 404)

    def test_dep_head_can_broadcast_to_roles(self):
        head = make_user("head", role="department_head")
        self.doc.assigned_to.add(head)
        self.client.force_login(head)
        self._post(audience=MessageAudience.ROLES, roles=["specialist"])
        self.assertEqual(ScheduledMessage.objects.get().status, MessageStatus.SENT)
        self.assertTrue(Notification.objects.filter(recipient=self.spec).exists())


class CancelViewTests(TestCase):
    def setUp(self):
        self.author = make_user("author")
        self.other = make_user("other")
        self.doc = Oferta.objects.create(**DOC)
        self.doc.assigned_to.add(self.author, self.other)
        self.msg = schedule_message(
            author=self.author, audience=MessageAudience.USERS, subject="s", body="b",
            users=[self.other], send_at=timezone.now() + timezone.timedelta(hours=3), target=self.doc,
        )

    def test_author_cancels(self):
        self.client.force_login(self.author)
        self.client.post(reverse("notification:message_cancel", args=[self.msg.pk]))
        self.msg.refresh_from_db()
        self.assertEqual(self.msg.status, MessageStatus.CANCELLED)

    def test_someone_else_cannot_cancel(self):
        self.client.force_login(self.other)
        response = self.client.post(reverse("notification:message_cancel", args=[self.msg.pk]))
        self.assertEqual(response.status_code, 403)
        self.msg.refresh_from_db()
        self.assertEqual(self.msg.status, MessageStatus.PENDING)


class SettingsViewTests(TestCase):
    def setUp(self):
        self.user = make_user("user")
        self.client.force_login(self.user)

    def test_own_settings_page_saves(self):
        url = reverse("notification:settings")
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.post(url, {"inapp_reminders": "on", "email_reminders": "on"})
        pref = NotificationPreference.objects.get(user=self.user)
        self.assertTrue(pref.email_reminders)
        self.assertFalse(pref.inapp_messages)

    def test_cannot_change_someone_else_without_permission(self):
        other = make_user("other")
        response = self.client.post(reverse("notification:user_preferences", args=[other.pk]), {})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(NotificationPreference.objects.filter(user=other).exists())

    def test_admin_changes_someone_else_from_user_tab(self):
        admin_user = make_user("boss", role="admin")
        other = make_user("other")
        self.client.force_login(admin_user)
        response = self.client.post(
            reverse("notification:user_preferences", args=[other.pk]),
            {"notif_inapp_assignment": "on", "username": "ignored"},
        )
        self.assertRedirects(
            response, reverse("admin:auth_user_change", args=[other.pk]) + "?tab=notifications",
            fetch_redirect_response=False,
        )
        pref = NotificationPreference.objects.get(user=other)
        self.assertTrue(pref.inapp_assignment)
        self.assertFalse(pref.inapp_status_change)
        other.refresh_from_db()
        self.assertEqual(other.username, "other")

    def test_user_tab_renders_switches(self):
        admin_user = make_user("boss", role="admin")
        self.client.force_login(admin_user)
        response = self.client.get(reverse("admin:auth_user_change", args=[self.user.pk]) + "?tab=notifications")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="notif_email_reminders"')
        self.assertContains(response, reverse("notification:user_preferences", args=[self.user.pk]))
