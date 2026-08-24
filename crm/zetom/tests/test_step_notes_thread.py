from django.contrib import admin
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from crm.clients.models import Client, Company, CompanyPersonLink
from crm.zetom.admin.children import OfertaAdmin
from crm.zetom.admin.requestmain import RequestMainAdmin
from crm.zetom.models import Oferta, RequestClientLink, RequestMain, StepNote

# claude — ManifestStaticFilesStorage requires collectstatic to resolve
# {% static %} lookups (including the ones the admin Media class makes);
# tests render the change form without running collectstatic first, so
# swap in a storage that serves straight from STATICFILES_DIRS. Same
# pattern as test_dupe_render_smoke.py / test_client_link_admin.py.
_SIMPLE_STATIC = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


class StepNotesThreadTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("admin", "admin@example.com", "pass12345")
        self.main = RequestMain.objects.create(
            first_name="Jan",
            last_name="Kowalski",
            phone="+48500100200",
            email="jan@example.com",
            company_name="Zetom",
        )
        self.oferta = Oferta.objects.create(
            from_main=self.main,
            first_name="Jan",
            last_name="Kowalski",
            phone="+48500100200",
            email="jan@example.com",
            company_name="Zetom",
        )

        self.main_admin = RequestMainAdmin(RequestMain, admin.site)
        self.oferta_admin = OfertaAdmin(Oferta, admin.site)

    def test_requestmain_context_includes_notes_from_child_documents(self):
        StepNote.objects.create(
            author=self.user,
            target=self.main,
            action="Main action",
            text="Main note",
            contacted_at=timezone.now(),
        )
        StepNote.objects.create(
            author=self.user,
            target=self.oferta,
            action="Offer action",
            text="Offer note",
            contacted_at=timezone.now(),
        )

        context = self.main_admin._build_step_notes_context(self.main)
        notes_texts = [note.text for note in context["step_notes"]]

        self.assertIn("Main note", notes_texts)
        self.assertIn("Offer note", notes_texts)

    def test_child_context_includes_notes_from_request_thread(self):
        StepNote.objects.create(
            author=self.user,
            target=self.main,
            action="Main action",
            text="Main thread note",
            contacted_at=timezone.now(),
        )
        StepNote.objects.create(
            author=self.user,
            target=self.oferta,
            action="Offer action",
            text="Offer thread note",
            contacted_at=timezone.now(),
        )

        context = self.oferta_admin._build_step_notes_context(self.oferta)
        notes_texts = [note.text for note in context["step_notes"]]

        self.assertIn("Main thread note", notes_texts)
        self.assertIn("Offer thread note", notes_texts)


# claude — Task 12: step_notes_persons (request clients + company persons,
# deduplicated) and the cc-* kind toggle markup in the shared modal.
class StepNoteModalTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            "admin2", "admin2@example.com", "pass12345",
        )
        self.main = RequestMain.objects.create(
            first_name="Jan",
            last_name="Kowalski",
            phone="+48500100200",
            email="jan@example.com",
            company_name="Zetom",
        )
        self.main_admin = RequestMainAdmin(RequestMain, admin.site)

    def test_modal_context_lists_request_persons(self):
        company = Company.objects.create(name="Zetom Sp. z o.o.", nip="1234563218")
        self.main.company = company
        self.main.save(update_fields=["company"])

        request_person = Client.objects.create(first_name="Anna", last_name="Nowak")
        RequestClientLink.objects.create(request=self.main, client=request_person)

        company_person = Client.objects.create(first_name="Piotr", last_name="Zielinski")
        CompanyPersonLink.objects.create(company=company, person=company_person)

        # claude — linked both ways (request AND company) must appear once.
        both_person = Client.objects.create(first_name="Ewa", last_name="Wojcik")
        RequestClientLink.objects.create(request=self.main, client=both_person)
        CompanyPersonLink.objects.create(company=company, person=both_person)

        context = self.main_admin._build_step_notes_context(self.main)
        persons = context["step_notes_persons"]

        self.assertEqual(
            {person.pk for person in persons},
            {request_person.pk, company_person.pk, both_person.pk},
        )
        self.assertEqual(len(persons), 3)

    def test_modal_context_excludes_unrelated_persons(self):
        unrelated = Client.objects.create(first_name="Obcy", last_name="Klient")

        context = self.main_admin._build_step_notes_context(self.main)

        self.assertNotIn(unrelated, context["step_notes_persons"])

    @override_settings(STORAGES=_SIMPLE_STATIC)
    def test_modal_renders_kind_toggle(self):
        self.client.force_login(self.user)
        url = reverse("admin:zetom_requestmain_change", args=[self.main.pk])

        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Log a conversation that already happened")
        self.assertContains(resp, "Plan a future contact")
