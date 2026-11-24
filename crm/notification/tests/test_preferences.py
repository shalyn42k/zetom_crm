# claude
"""NotificationPreference (muting, settings page, admin user tab), the
assignment notification, reminder email copies and plain-text escaping."""
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from crm.notification.models import (
    Notification, NotificationKind, NotificationPreference,
)
from crm.notification.services import preferences
from crm.users.models import Role

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


# claude
class PreferenceFilterTests(TestCase):
    def setUp(self):
        self.a = make_user("a")
        self.b = make_user("b")

    def test_defaults_without_rows(self):
        self.assertEqual(preferences.filter_inapp([self.a, self.b], NotificationKind.ASSIGNMENT), [self.a, self.b])
        # email reminders are opt-in
        self.assertEqual(preferences.filter_email([self.a], NotificationKind.REMINDER), [])

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


# claude
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
        self.assertFalse(pref.inapp_assignment)

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



# claude
class ClientReminderEscapingTests(TestCase):
    def test_quotes_reach_the_client_unescaped(self):
        from crm.notification.services.followup_reminders import (
            process_due_followups,
        )
        from crm.zetom.models import RequestMain, StepNote

        author = make_user("author")
        req = RequestMain.objects.create(**DOC)
        text = 'Don\'t forget the "A&B" offer'
        note = StepNote.objects.create(
            author=author, target=req, kind=StepNote.Kind.REMINDER, text=text, action="Reminder",
            next_contact_at=timezone.now() - timezone.timedelta(minutes=1),
            notify=StepNote.Notify.CLIENT, client_email="jan@client.pl",
        )
        mail.outbox.clear()
        process_due_followups()
        self.assertIn(text, mail.outbox[0].body)
        note.refresh_from_db()
        self.assertIsNotNone(note.done_at)
