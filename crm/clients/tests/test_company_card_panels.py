# claude
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from crm.clients.models import Client, Company, CompanyPersonLink
from crm.status_manager.services.statuses import RequestStatus
from crm.zetom.models import DepartmentsVariants, RequestMain, StepNote
from crm.zetom.services.step_notes import create_step_note


class CompanyCardPanelsTest(TestCase):
    """Phase 3a Task 3: Powiązane zgłoszenia + Historia kontaktów panels
    must render real RequestMain/ClientInteraction rows, not the Task 1/2
    empty scaffolds."""

    def setUp(self):
        self.user = User.objects.create_superuser("staff", "s@s.pl", "pass12345")
        self.client.force_login(self.user)
        self.company = Company.objects.create(name="Zetom Sp. z o.o.", nip="1234563218")
        self.person = Client.objects.create(first_name="Jan", last_name="Kowalski")
        CompanyPersonLink.objects.create(
            company=self.company, person=self.person, position="Kierownik",
        )

    def test_requests_and_history_panels_render_real_data(self):
        request_main = RequestMain.objects.create(
            phone="+48501600300", email="jan@zetom.pl",
            company=self.company, status=RequestStatus.active,
            departments=[DepartmentsVariants.DEPARTMENT_1],
        )
        create_step_note(
            author=self.user,
            kind=StepNote.Kind.CONTACT,
            channel=StepNote.Channel.CALL,
            text="Rozmowa o ofercie kalibracji",
            person=self.person,
            contact_person="Jan Kowalski",
            contacted_at=timezone.now(),
            target=request_main,
        )

        url = reverse("admin:clients_company_change", args=[self.company.pk])
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Related requests")   # EN locale (LANGUAGE_CODE=en)
        self.assertContains(resp, "Contact history")
        self.assertContains(resp, f"Request no. {request_main.pk}")
        self.assertContains(resp, "Rozmowa o ofercie kalibracji")

    # claude — Final-fix-round: a note carrying both action and text must
    # render both on the company card's "Historia kontaktów" panel too —
    # action as the lead line, text below (same as the zetom document-card
    # modal already does for entry.action / entry.text).
    #
    # count=2, not just assertContains: the same note also feeds the shared
    # work-log modal's (already-correct) hidden timeline included at the
    # bottom of this panel, which already renders entry.action. A plain
    # assertContains would pass on that alone even before this fix — count=2
    # pins that the *visible* "Historia kontaktów" row renders it too.
    def test_history_note_with_action_and_text_renders_both(self):
        create_step_note(
            author=self.user, kind=StepNote.Kind.CONTACT,
            action="Ustalono termin", text="Klient prosi o kontakt jutro",
            person=self.person, contacted_at=timezone.now(),
        )

        url = reverse("admin:clients_company_change", args=[self.company.pk])
        resp = self.client.get(url)

        self.assertContains(resp, "Ustalono termin", count=2)
        self.assertContains(resp, "Klient prosi o kontakt jutro", count=2)

    # claude — Final-fix-round: regression guard — a plain note with only
    # text (no action) must keep rendering exactly as before, with no stray
    # empty markup for the missing action.
    def test_history_note_with_only_text_renders_as_before(self):
        create_step_note(
            author=self.user, kind=StepNote.Kind.CONTACT,
            text="Rozmowa telefoniczna",
            person=self.person, contacted_at=timezone.now(),
        )

        url = reverse("admin:clients_company_change", args=[self.company.pk])
        resp = self.client.get(url)

        self.assertContains(resp, "Rozmowa telefoniczna")
        self.assertNotContains(resp, "<strong></strong>")

    def test_unrelated_company_history_not_leaked(self):
        # A ClientInteraction for a person of another firm must not show up
        # on this company's card (regression guard for the M2M filter).
        other_company = Company.objects.create(name="Other Sp.")
        other_person = Client.objects.create(first_name="Anna")
        CompanyPersonLink.objects.create(company=other_company, person=other_person)
        create_step_note(
            author=None,
            kind=StepNote.Kind.CONTACT,
            channel=StepNote.Channel.EMAIL,
            text="Nie powinno się tu pojawić",
            person=other_person,
            contacted_at=timezone.now(),
        )

        url = reverse("admin:clients_company_change", args=[self.company.pk])
        resp = self.client.get(url)

        self.assertNotContains(resp, "Nie powinno się tu pojawić")
