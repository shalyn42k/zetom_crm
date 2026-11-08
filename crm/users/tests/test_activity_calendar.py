from datetime import datetime, timedelta, timezone as datetime_timezone
from zoneinfo import ZoneInfo

from django.contrib.admin.models import ADDITION, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import override

from crm.status_manager.models import ChildDocumentDeletion, StatusHistory
from crm.users.models import Role
from crm.zetom.models import Oferta, RequestMain, StepNote


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class ActivityCalendarTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="calendar_user", is_staff=True)
        cls.user.profile.role = Role.objects.get(code="specialist")
        cls.user.profile.departments = ["DEPARTMENT_0"]
        cls.user.profile.otp_exempt = True
        cls.user.profile.save()
        cls.other = User.objects.create_user(username="calendar_other", is_staff=True)
        cls.visible = RequestMain.objects.create(
            company_name="Visible request", phone="+48501600300", email="test@example.com",
            departments=["DEPARTMENT_0"],
        )
        cls.hidden = RequestMain.objects.create(
            company_name="Hidden request", phone="+48501600300", email="test@example.com",
            departments=["DEPARTMENT_1"],
        )
        cls.doc = Oferta.objects.create(
            from_main=cls.visible, company_name="Visible offer", phone="+48501600300",
            email="test@example.com", departments=["DEPARTMENT_0"],
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.when = timezone.make_aware(datetime(2026, 10, 8, 12, 0), ZoneInfo("Europe/Warsaw"))

    def note(self, target, author, text, when=None):
        note = StepNote.objects.create(
            target=target, author=author, kind=StepNote.Kind.CONTACT,
            contacted_at=self.when, text=text,
        )
        StepNote.objects.filter(pk=note.pk).update(created_at=when or self.when)
        return note

    def reminder(self, target, author, text, **kwargs):
        return StepNote.objects.create(
            target=target, author=author, kind=StepNote.Kind.REMINDER,
            next_contact_at=self.when, text=text, **kwargs,
        )

    def test_calendar_combines_events_deduplicates_and_filters_by_user_and_visibility(self):
        self.note(self.visible, self.user, "My first note")
        self.note(self.doc, self.user, "My document note")
        self.note(self.hidden, self.user, "Hidden note")
        self.note(self.visible, self.other, "Other employee note")
        history = self.visible.history.first()
        self.visible.history.filter(pk=history.pk).update(
            history_user=self.user, history_date=self.when,
        )
        status = StatusHistory.objects.create(
            request=self.visible, old_status="active", new_status="open",
            changed_by=self.user, reason="Handled",
        )
        StatusHistory.objects.filter(pk=status.pk).update(changed_at=self.when)
        log = LogEntry.objects.log_actions(
            user_id=self.user.pk,
            queryset=Oferta.objects.filter(pk=self.doc.pk),
            action_flag=ADDITION,
            change_message="Added.",
            single_object=True,
        )
        LogEntry.objects.filter(pk=log.pk).update(action_time=self.when)
        main_log = LogEntry.objects.log_actions(
            user_id=self.user.pk, queryset=RequestMain.objects.filter(pk=self.visible.pk),
            action_flag=ADDITION, change_message="Added.", single_object=True,
        )
        LogEntry.objects.filter(pk=main_log.pk).update(action_time=self.when)

        response = self.client.get(reverse("activity_calendar"), {"date": "2026-10-08"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["day_count"], 1)
        self.assertEqual(response.context["month_count"], 1)
        self.assertEqual(response.context["event_count"], 6)
        self.assertContains(response, "My first note")
        self.assertContains(response, "My document note")
        self.assertContains(response, "Handled")
        self.assertNotContains(response, "Hidden note")
        self.assertNotContains(response, "Other employee note")
        self.assertContains(response, reverse("admin:zetom_requestmain_change", args=[self.visible.pk]))

    def test_distinct_counts_across_days_and_local_midnight(self):
        self.note(self.visible, self.user, "Day one")
        after_midnight = datetime(2026, 10, 8, 22, 30, tzinfo=datetime_timezone.utc)
        self.note(self.visible, self.user, "Day two", after_midnight)
        response = self.client.get(reverse("activity_calendar"), {"date": "2026-10-09"})
        self.assertEqual(response.context["month_count"], 1)
        self.assertEqual(response.context["day_count"], 1)
        self.assertContains(response, "Day two")
        self.assertNotContains(response, "Day one")
        counts = {day["date"].isoformat(): day["count"] for week in response.context["weeks"] for day in week}
        self.assertEqual(counts["2026-10-08"], 1)
        self.assertEqual(counts["2026-10-09"], 1)

    def test_inaccessible_document_is_excluded_and_deletion_is_recorded(self):
        hidden_doc = Oferta.objects.create(
            from_main=self.visible, company_name="Hidden offer", phone="+48501600300",
            email="test@example.com", departments=["DEPARTMENT_1"],
        )
        self.note(hidden_doc, self.user, "Hidden document note")
        deletion = ChildDocumentDeletion.objects.create(
            from_main=self.visible, deleted_by=self.user, document_type="oferta",
            document_repr="Old offer", reason="Duplicate",
        )
        ChildDocumentDeletion.objects.filter(pk=deletion.pk).update(deleted_at=self.when)
        response = self.client.get(reverse("activity_calendar"), {"date": "2026-10-08"})
        self.assertEqual(response.context["day_count"], 1)
        self.assertEqual(response.context["event_count"], 1)
        self.assertContains(response, "Old offer")
        self.assertNotContains(response, "Hidden document note")

    def test_request_history_includes_field_changes(self):
        self.visible.history.update(history_date=self.when - timedelta(days=1))
        self.visible.company_name = "Changed company"
        self.visible.save()
        history = self.visible.history.first()
        self.visible.history.filter(pk=history.pk).update(history_user=self.user, history_date=self.when)
        response = self.client.get(reverse("activity_calendar"), {"date": "2026-10-08"})
        self.assertContains(response, "Visible request")
        self.assertContains(response, "Changed company")

    def test_navigation_and_empty_date(self):
        response = self.client.get(reverse("activity_calendar"), {"date": "2026-01-15"})
        self.assertEqual(response.context["previous"].isoformat(), "2025-12-01")
        self.assertEqual(response.context["next"].isoformat(), "2026-02-01")
        self.assertEqual(response.context["day_count"], 0)
        self.assertContains(response, "No recorded activity on this day.")

    def test_access_and_bad_dates(self):
        for value in ("not-a-date", "2026-02-30", "0001-01-01", "9999-12-01", "20261008"):
            self.assertEqual(self.client.get(reverse("activity_calendar"), {"date": value}).status_code, 400)
        self.user.profile.role = None
        self.user.profile.save()
        self.assertEqual(self.client.get(reverse("activity_calendar")).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("activity_calendar")).status_code, 302)

    def test_cancelled_request_uses_archive_link(self):
        self.visible.status = "cancelled"
        self.visible.save()
        self.note(self.visible, self.user, "Cancelled note")
        response = self.client.get(reverse("activity_calendar"), {"date": "2026-10-08"})
        self.assertContains(response, reverse("admin:zetom_cancelledrequest_change", args=[self.visible.pk]))

    def test_dashboard_links_to_calendar(self):
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, reverse("activity_calendar"))

    def test_polish_translation(self):
        self.note(self.visible, self.user, "First event", self.when)
        self.note(self.visible, self.user, "Second event", self.when)
        self.client.cookies["django_language"] = "pl"
        with override("pl"):
            response = self.client.get(reverse("activity_calendar"), {"date": "2026-10-08"})
        self.assertContains(response, "Mój kalendarz aktywności")
        self.assertContains(response, "Zaplanowane przypomnienia")
        self.assertContains(response, "2 zdarzenia")

    def test_activity_is_collapsed_with_count_latest_time_and_link(self):
        self.note(self.visible, self.user, "First event", self.when)
        self.note(self.visible, self.user, "Latest event", self.when + timedelta(minutes=30))
        response = self.client.get(reverse("activity_calendar"), {"date": "2026-10-08"})
        self.assertContains(response, '<details class="activity-calendar__request">')
        self.assertContains(response, "2 events")
        self.assertContains(response, "12:30")
        self.assertContains(response, "First event")
        self.assertContains(response, "Latest event")
        self.assertContains(response, reverse("admin:zetom_requestmain_change", args=[self.visible.pk]))

    def test_planned_reminders_are_separate_from_activity_and_use_local_due_date(self):
        due = datetime(2026, 10, 8, 22, 30, tzinfo=datetime_timezone.utc)
        reminder = self.reminder(self.visible, self.user, "Upcoming call", notify=StepNote.Notify.SELF)
        StepNote.objects.filter(pk=reminder.pk).update(
            created_at=self.when - timedelta(days=1), next_contact_at=due,
        )
        response = self.client.get(reverse("activity_calendar"), {"date": "2026-10-09"})
        self.assertEqual(response.context["day_count"], 0)
        self.assertEqual(response.context["event_count"], 1)
        self.assertEqual(len(response.context["reminders"]), 1)
        self.assertContains(response, "Upcoming call")
        self.assertContains(response, "00:30")
        self.assertContains(response, "No recorded activity on this day.")
        day = next(day for week in response.context["weeks"] for day in week if day["date"].isoformat() == "2026-10-09")
        self.assertEqual(day["count"], 0)
        self.assertEqual(day["reminder_count"], 1)
        created_day = self.client.get(reverse("activity_calendar"), {"date": "2026-10-07"})
        self.assertEqual(created_day.context["day_count"], 1)
        self.assertEqual(len(created_day.context["reminders"]), 0)

    def test_planned_reminders_follow_recipient_and_visibility_rules(self):
        explicit = self.reminder(self.doc, self.other, "Assigned to me", notify=StepNote.Notify.USERS)
        explicit.notify_users.add(self.user)
        other = self.reminder(self.visible, self.user, "Assigned to someone else", notify=StepNote.Notify.USERS)
        other.notify_users.add(self.other)
        self.reminder(self.visible, self.other, "For my role", notify=StepNote.Notify.ROLES, notify_roles=["specialist"])
        self.reminder(self.hidden, self.user, "Hidden request reminder", notify=StepNote.Notify.SELF)
        hidden_doc = Oferta.objects.create(
            from_main=self.visible, company_name="Hidden offer", phone="+48501600300",
            email="test@example.com", departments=["DEPARTMENT_1"],
        )
        self.reminder(hidden_doc, self.user, "Hidden document reminder", notify=StepNote.Notify.SELF)
        self.reminder(self.visible, self.user, "Completed reminder", notify=StepNote.Notify.SELF, done_at=self.when)
        self.reminder(self.visible, self.user, "Client message", notify=StepNote.Notify.CLIENT, client_email="client@example.com")
        self.reminder(self.visible, self.other, "Other client message", notify=StepNote.Notify.CLIENT, client_email="client@example.com")

        response = self.client.get(reverse("activity_calendar"), {"date": "2026-10-08"})
        texts = {item["note"].text for item in response.context["reminders"]}
        self.assertEqual(texts, {"Assigned to me", "For my role", "Client message"})
        self.assertContains(response, "Scheduled client email")
        self.assertNotContains(response, "Hidden request reminder")
        self.assertNotContains(response, "Hidden document reminder")

    def test_default_recipients_use_owner_then_assignees_then_author(self):
        self.reminder(self.doc, self.other, "Default reminder")
        self.visible.owners.add(self.user)
        response = self.client.get(reverse("activity_calendar"), {"date": "2026-10-08"})
        self.assertEqual([item["note"].text for item in response.context["reminders"]], ["Default reminder"])
        self.visible.owners.clear()
        self.doc.assigned_to.add(self.other)
        response = self.client.get(reverse("activity_calendar"), {"date": "2026-10-08"})
        self.assertEqual(response.context["reminders"], [])
        self.doc.assigned_to.clear()
        self.visible.assigned_to.add(self.user)
        response = self.client.get(reverse("activity_calendar"), {"date": "2026-10-08"})
        self.assertEqual([item["note"].text for item in response.context["reminders"]], ["Default reminder"])

    def test_done_reminder_disappears_from_plan_but_creation_remains(self):
        reminder = self.reminder(self.visible, self.user, "Done later", notify=StepNote.Notify.SELF)
        StepNote.objects.filter(pk=reminder.pk).update(created_at=self.when, done_at=self.when)
        response = self.client.get(reverse("activity_calendar"), {"date": "2026-10-08"})
        self.assertEqual(response.context["reminders"], [])
        self.assertContains(response, "Done later")
