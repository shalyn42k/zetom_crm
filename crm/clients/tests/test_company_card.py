# claude
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from crm.clients.models import Client, Company, CompanyPersonLink, SupplierType
from crm.users.models import Permission
from crm.zetom.models import StepNote
from crm.zetom.services.step_notes import create_step_note


class CompanyCardTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("staff", "s@s.pl", "pass12345")
        self.client.force_login(self.user)

    def test_card_renders_company_basics(self):
        company = Company.objects.create(
            name="Zetom Sp. z o.o.", nip="1234563218", regon="123456785",
            type_supplier=SupplierType.REGIONAL, city="Katowice", email="biuro@zetom.pl",
        )
        url = reverse("admin:clients_company_change", args=[company.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Zetom Sp. z o.o.")
        self.assertContains(resp, "1234563218")
        self.assertContains(resp, "Basic data")       # EN locale (LANGUAGE_CODE=en)
        self.assertContains(resp, "Contact persons")


# claude — Task 13: "Zaplanowane" panel + "Dodaj kontakt" write controls on
# the Company card. Unlike the Person card, the create flow has to pick a
# person from the company first (no company-addressed urls exist — see
# task-9-brief.md), and reminders here can belong to different persons, so
# each row's checkmark must point at its own owning person. See
# task-13-brief.md.
class CompanyCardStepNotesTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("staff13", "s13@s.pl", "pass12345")
        self.client.force_login(self.user)
        self.company = Company.objects.create(name="Zetom Sp. z o.o.", nip="1234563218")
        self.person = Client.objects.create(first_name="Jan", last_name="Kowalski")
        CompanyPersonLink.objects.create(company=self.company, person=self.person, position="Kierownik")
        self.url = reverse("admin:clients_company_change", args=[self.company.pk])

    def test_company_card_renders_reminders_section(self):
        note = create_step_note(
            author=self.user, kind=StepNote.Kind.REMINDER, text="Oddzwonić w sprawie oferty",
            person=self.person, next_contact_at=timezone.now() + timedelta(days=1),
        )

        resp = self.client.get(self.url, HTTP_HOST="127.0.0.1")

        self.assertContains(resp, "Zaplanowane")
        self.assertContains(resp, "Oddzwonić w sprawie oferty")
        done_url = reverse(
            "admin:clients_client_step_note_done", args=[self.person.pk, note.pk],
        )
        self.assertContains(resp, done_url)

    def test_company_card_hides_reminders_section_when_empty(self):
        resp = self.client.get(self.url, HTTP_HOST="127.0.0.1")

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Zaplanowane")
        self.assertContains(resp, "Brak zaplanowanych przypomnień.")

    def test_overdue_reminder_gets_overdue_modifier(self):
        create_step_note(
            author=self.user, kind=StepNote.Kind.REMINDER, text="Przeterminowane",
            person=self.person, next_contact_at=timezone.now() - timedelta(days=1),
        )

        resp = self.client.get(self.url, HTTP_HOST="127.0.0.1")

        self.assertContains(resp, "hev overdue")

    def test_reminders_from_different_persons_link_their_own_checkmark(self):
        second_person = Client.objects.create(first_name="Piotr", last_name="Nowak")
        CompanyPersonLink.objects.create(company=self.company, person=second_person)
        note_a = create_step_note(
            author=self.user, kind=StepNote.Kind.REMINDER, text="Do Jana",
            person=self.person, next_contact_at=timezone.now() + timedelta(days=1),
        )
        note_b = create_step_note(
            author=self.user, kind=StepNote.Kind.REMINDER, text="Do Piotra",
            person=second_person, next_contact_at=timezone.now() + timedelta(days=1),
        )

        resp = self.client.get(self.url, HTTP_HOST="127.0.0.1")

        self.assertContains(resp, reverse(
            "admin:clients_client_step_note_done", args=[self.person.pk, note_a.pk],
        ))
        self.assertContains(resp, reverse(
            "admin:clients_client_step_note_done", args=[second_person.pk, note_b.pk],
        ))

    def test_company_card_shows_add_contact_button_for_editor(self):
        resp = self.client.get(self.url, HTTP_HOST="127.0.0.1")

        self.assertContains(resp, "Dodaj kontakt")
        # claude — the create modal has no company-addressed url of its own;
        # the picker must offer this company's own persons to attach to.
        self.assertContains(resp, "Jan Kowalski")

    def test_company_card_hides_add_contact_button_for_viewer(self):
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

    def test_company_card_hides_done_checkmark_for_viewer(self):
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
