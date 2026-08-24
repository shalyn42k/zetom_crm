# claude
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from crm.clients.models import Client, Company, CompanyPersonLink
from crm.users.models import Permission
from crm.zetom.models import StepNote
from crm.zetom.services.step_notes import create_step_note


class PersonCardTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("staff", "s@s.pl", "pass12345")
        self.client.force_login(self.user)

    def test_card_shows_person_and_firmy(self):
        person = Client.objects.create(first_name="Jan", last_name="Kowalski", email="j@z.pl")
        company = Company.objects.create(name="Zetom", nip="1234563218")
        CompanyPersonLink.objects.create(company=company, person=person, position="Kierownik")
        resp = self.client.get(reverse("admin:clients_client_change", args=[person.pk]), HTTP_HOST="127.0.0.1")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Jan")
        self.assertContains(resp, "Personal data")  # EN locale (LANGUAGE_CODE=en)
        self.assertContains(resp, "Companies")
        self.assertContains(resp, "Zetom")
        self.assertContains(resp, "Kierownik")

    def test_person_save_updates_fields(self):
        person = Client.objects.create(first_name="Old")
        url = reverse("admin:clients_client_person_save", args=[person.pk])
        resp = self.client.post(url, {"first_name": "New", "last_name": "Name", "email": "n@n.pl"}, HTTP_HOST="127.0.0.1")
        self.assertTrue(resp.json()["ok"])
        person.refresh_from_db()
        self.assertEqual(person.first_name, "New")


# claude — Task 13: "Zaplanowane" panel + "Dodaj kontakt" write controls on
# the Person card. See task-13-brief.md.
class PersonCardStepNotesTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("staff13", "s13@s.pl", "pass12345")
        self.client.force_login(self.user)
        self.person = Client.objects.create(first_name="Jan", last_name="Kowalski")
        self.url = reverse("admin:clients_client_change", args=[self.person.pk])

    def test_person_card_renders_reminders_section(self):
        note = create_step_note(
            author=self.user, kind=StepNote.Kind.REMINDER, text="Oddzwonić w sprawie oferty",
            person=self.person, next_contact_at=timezone.now() + timedelta(days=1),
        )

        resp = self.client.get(self.url, HTTP_HOST="127.0.0.1")

        self.assertContains(resp, "Scheduled")
        self.assertContains(resp, "Oddzwonić w sprawie oferty")
        done_url = reverse(
            "admin:clients_client_step_note_done", args=[self.person.pk, note.pk],
        )
        self.assertContains(resp, done_url)

    def test_person_card_hides_reminders_section_when_empty(self):
        resp = self.client.get(self.url, HTTP_HOST="127.0.0.1")

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Scheduled")
        self.assertContains(resp, "No scheduled reminders.")

    def test_overdue_reminder_gets_overdue_modifier(self):
        create_step_note(
            author=self.user, kind=StepNote.Kind.REMINDER, text="Przeterminowane",
            person=self.person, next_contact_at=timezone.now() - timedelta(days=1),
        )

        resp = self.client.get(self.url, HTTP_HOST="127.0.0.1")

        self.assertContains(resp, "hev overdue")

    def test_person_card_shows_add_contact_button_for_editor(self):
        resp = self.client.get(self.url, HTTP_HOST="127.0.0.1")

        self.assertContains(resp, "Add contact")

    def test_person_card_hides_add_contact_button_for_viewer(self):
        viewer = User.objects.create_user("viewer13", "v13@v.pl", "pass12345", is_staff=True)
        profile = viewer.profile
        profile.otp_exempt = True
        profile.role = None
        profile.save()
        profile.extra_permissions.add(Permission.objects.get(code="view_clients"))
        self.client.force_login(viewer)

        resp = self.client.get(self.url, HTTP_HOST="127.0.0.1")

        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Dodaj kontakt")

    def test_person_card_hides_done_checkmark_for_viewer(self):
        note = create_step_note(
            author=self.user, kind=StepNote.Kind.REMINDER, text="Oddzwonić",
            person=self.person, next_contact_at=timezone.now() + timedelta(days=1),
        )
        viewer = User.objects.create_user("viewer13b", "v13b@v.pl", "pass12345", is_staff=True)
        profile = viewer.profile
        profile.otp_exempt = True
        profile.role = None
        profile.save()
        profile.extra_permissions.add(Permission.objects.get(code="view_clients"))
        self.client.force_login(viewer)

        resp = self.client.get(self.url, HTTP_HOST="127.0.0.1")

        self.assertEqual(resp.status_code, 200)
        done_url = reverse(
            "admin:clients_client_step_note_done", args=[self.person.pk, note.pk],
        )
        self.assertNotContains(resp, done_url)
