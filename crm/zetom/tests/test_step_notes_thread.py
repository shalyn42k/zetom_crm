from django.contrib import admin
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from crm.zetom.admin.children import OfertaAdmin
from crm.zetom.admin.requestmain import RequestMainAdmin
from crm.zetom.models import Oferta, RequestMain, StepNote


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
