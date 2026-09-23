# ──────────────────────────────────────────────────────────────────────────────
# ТЕСТЫ document chain (Task 10 + Task 11)
#
# Task 10 — мягкая цепочка Oferta -> Zlecenie -> Wniosek:
#   • Zlecenie.from_oferta / Wniosek.from_zlecenie — nullable FK, SET_NULL.
#   • Удаление родителя не убивает дочерний документ — просто обнуляет ссылку.
#   • from_main никогда не трогается цепочкой (это отдельная связь).
#
# Task 10 tests: DocumentChainModelTests.
# ──────────────────────────────────────────────────────────────────────────────

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from safedelete.config import HARD_DELETE

from crm.status_manager.models import ChildDocumentDeletion
from crm.status_manager.services.statuses import RequestStatus, Status
from crm.zetom.models import (
    Oferta, RequestMain, Wniosek, Zlecenie,
)

User = get_user_model()

BASE_DATA = {
    "phone": "+48501600300",
    "email": "contact@zetom.pl",
}


# ─────────────────────────── Task 10: модельная цепочка ───────────────────────

class DocumentChainModelTests(TestCase):
    """Zlecenie.from_oferta / Wniosek.from_zlecenie — мягкая цепочка."""

    def setUp(self):
        self.main = RequestMain.objects.create(**BASE_DATA)
        self.oferta = Oferta.objects.create(**BASE_DATA, from_main=self.main)
        self.zlecenie = Zlecenie.objects.create(**BASE_DATA, from_main=self.main)

    # ---- Zlecenie.from_oferta ----

    def test_zlecenie_can_be_created_without_oferta(self):
        z = Zlecenie.objects.create(**BASE_DATA, from_main=self.main, from_oferta=None)
        self.assertIsNone(z.from_oferta)

    def test_zlecenie_links_back_to_oferta(self):
        z = Zlecenie.objects.create(**BASE_DATA, from_main=self.main, from_oferta=self.oferta)
        self.assertIn(z, self.oferta.zlecenia.all())

    def test_deleting_oferta_keeps_zlecenie(self):
        z = Zlecenie.objects.create(**BASE_DATA, from_main=self.main, from_oferta=self.oferta)
        self.oferta.delete(force_policy=HARD_DELETE)
        z.refresh_from_db()
        self.assertIsNone(z.from_oferta)
        self.assertEqual(z.from_main, self.main)

    # ---- Wniosek.from_zlecenie ----

    def test_wniosek_can_be_created_without_zlecenie(self):
        w = Wniosek.objects.create(**BASE_DATA, from_main=self.main, from_zlecenie=None)
        self.assertIsNone(w.from_zlecenie)

    def test_wniosek_links_back_to_zlecenie(self):
        w = Wniosek.objects.create(**BASE_DATA, from_main=self.main, from_zlecenie=self.zlecenie)
        self.assertIn(w, self.zlecenie.wnioski.all())

    def test_deleting_zlecenie_keeps_wniosek(self):
        w = Wniosek.objects.create(**BASE_DATA, from_main=self.main, from_zlecenie=self.zlecenie)
        self.zlecenie.delete(force_policy=HARD_DELETE)
        w.refresh_from_db()
        self.assertIsNone(w.from_zlecenie)
        self.assertEqual(w.from_main, self.main)


# claude — Fix-round: CloseOfertaOnZlecenieTests and
# ChildDocumentChainActionTests (Task 11's "create the next document"
# chain buttons + their auto-close side effect) removed along with the
# feature itself — a single Oferta/Zlecenie can have more than one
# Zlecenie/Wniosek filed against it, so "creating the next doc always
# closes this one" didn't hold. See status_orchestration.py's module
# docstring and children.py's module docstring for the full story.
# Smoke coverage for the chain-button templates went with them; the
# remaining button on these forms ("Mark as done") is covered below by
# MarkDoneActionTests.


# ───────────────────────── "Mark as done" button ───────────────────────────

class MarkDoneActionTests(TestCase):
    """Status editing is locked out of the Oferta/Zlecenie/Wniosek forms
    entirely, and Wniosek has no auto-close hook (nothing is ever created
    from it) — mark_done_action is the only way any of the three can reach
    `done` without an auto-close chain event."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(
            username="admin3", email="a3@a.com", password="x"
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.main = RequestMain.objects.create(**BASE_DATA, company_name="Zetom")

    def test_wniosek_mark_done_action(self):
        wniosek = Wniosek.objects.create(**BASE_DATA, from_main=self.main)
        url = reverse("admin:zetom_wniosek_mark_done", args=[wniosek.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        wniosek.refresh_from_db()
        self.assertEqual(wniosek.status, Status.done)

    def test_mark_done_recomputes_parent_status(self):
        Oferta.objects.create(**BASE_DATA, from_main=self.main, status=Status.done)
        Zlecenie.objects.create(**BASE_DATA, from_main=self.main, status=Status.done)
        wniosek = Wniosek.objects.create(**BASE_DATA, from_main=self.main)
        self.client.post(reverse("admin:zetom_wniosek_mark_done", args=[wniosek.pk]))
        self.main.refresh_from_db()
        self.assertEqual(self.main.status, RequestStatus.closed)

    def test_mark_done_get_does_not_change_status(self):
        wniosek = Wniosek.objects.create(**BASE_DATA, from_main=self.main)
        url = reverse("admin:zetom_wniosek_mark_done", args=[wniosek.pk])
        self.client.get(url)
        wniosek.refresh_from_db()
        self.assertEqual(wniosek.status, Status.new)

    def test_oferta_change_form_renders_mark_done_button(self):
        oferta = Oferta.objects.create(**BASE_DATA, from_main=self.main)
        url = reverse("admin:zetom_oferta_change", args=[oferta.pk])
        response = self.client.get(url)
        self.assertContains(
            response, reverse("admin:zetom_oferta_mark_done", args=[oferta.pk])
        )

    def test_mark_done_button_hidden_once_already_done(self):
        wniosek = Wniosek.objects.create(**BASE_DATA, from_main=self.main, status=Status.done)
        url = reverse("admin:zetom_wniosek_change", args=[wniosek.pk])
        response = self.client.get(url)
        self.assertNotContains(
            response, reverse("admin:zetom_wniosek_mark_done", args=[wniosek.pk])
        )


# ───────────────────── Child document delete requires a reason ────────────────

class ChildDocumentDeleteReasonTests(TestCase):
    """Deleting an Oferta/Zlecenie/Wniosek from its change form requires a
    reason, logged to ChildDocumentDeletion since the row itself is gone
    after a hard delete."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(
            username="admin2", email="a2@a.com", password="x"
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.main = RequestMain.objects.create(**BASE_DATA, company_name="Zetom")
        self.oferta = Oferta.objects.create(
            **BASE_DATA, from_main=self.main, company_name="Zetom",
        )

    def test_delete_without_reason_does_not_delete(self):
        url = reverse("admin:zetom_oferta_delete", args=[self.oferta.pk])
        response = self.client.post(url, {"reason": ""})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Oferta.objects.filter(pk=self.oferta.pk).exists())
        self.assertEqual(ChildDocumentDeletion.objects.count(), 0)

    def test_delete_with_reason_deletes_and_logs(self):
        url = reverse("admin:zetom_oferta_delete", args=[self.oferta.pk])
        response = self.client.post(url, {"reason": "Duplicate entry"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Oferta.objects.filter(pk=self.oferta.pk).exists())

        entry = ChildDocumentDeletion.objects.get(from_main=self.main)
        self.assertEqual(entry.reason, "Duplicate entry")
        self.assertEqual(entry.document_type, "Oferta")
        self.assertEqual(entry.deleted_by, self.user)

    def test_delete_recomputes_parent_status(self):
        Zlecenie.objects.create(**BASE_DATA, from_main=self.main, status=Status.done)
        Wniosek.objects.create(**BASE_DATA, from_main=self.main, status=Status.done)
        self.oferta.status = Status.done
        self.oferta.save(update_fields=["status"])
        self.main.status = RequestStatus.closed
        self.main.save(update_fields=["status"])

        url = reverse("admin:zetom_oferta_delete", args=[self.oferta.pk])
        self.client.post(url, {"reason": "Mistake"})

        self.main.refresh_from_db()
        # Oferta is gone, so not all three document types exist anymore —
        # the parent can no longer be `closed`.
        self.assertEqual(self.main.status, RequestStatus.active)
