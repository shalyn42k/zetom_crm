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

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from safedelete.config import HARD_DELETE

from crm.status_manager.models import StatusHistory
from crm.status_manager.services.statuses import RequestStatus, Status
from crm.zetom.models import (
    DepartmentsVariants, Oferta, RequestMain, Wniosek, Zlecenie,
)
from crm.zetom.services.status_orchestration import close_oferta_on_zlecenie

User = get_user_model()

BASE_DATA = {
    "phone": "+48501600300",
    "email": "contact@zetom.pl",
}

_SIMPLE_STATIC = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
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


# ─────────────────────────── Task 11: close_oferta_on_zlecenie ────────────────

class CloseOfertaOnZlecenieTests(TestCase):
    """close_oferta_on_zlecenie — system-driven переход мимо FSM.

    Не через change_status/handle_child_change: их transitions-таблица не
    пускает new/in_progress -> done напрямую (см. status_service.py:24-29).
    Пишет одну строку StatusHistory (аудит на уровне родительской RequestMain,
    т.к. у StatusHistory.request нет FK на дочерние документы) и каскадит
    родителя через update_parent.
    """

    def setUp(self):
        self.main = RequestMain.objects.create(**BASE_DATA)
        self.oferta = Oferta.objects.create(**BASE_DATA, from_main=self.main)
        self.user = User.objects.create_user(username="worker", password="x")

    def test_sets_status_done_from_new(self):
        # new -> done напрямую невозможен через FSM, но close_oferta_on_zlecenie
        # обязан это сделать — иначе оферта, созданная и сразу переведённая
        # в заказ, никогда не закроется.
        self.assertEqual(self.oferta.status, Status.new)
        close_oferta_on_zlecenie(self.oferta, self.user)
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.status, Status.done)

    def test_writes_single_status_history_row(self):
        close_oferta_on_zlecenie(self.oferta, self.user)
        entries = StatusHistory.objects.filter(request=self.main)
        self.assertEqual(entries.count(), 1)
        entry = entries.first()
        self.assertEqual(entry.old_status, Status.new)
        self.assertEqual(entry.new_status, Status.done)
        self.assertEqual(entry.changed_by, self.user)

    def test_cascades_to_parent_via_update_parent(self):
        # Оферта — единственный ребёнок; после done update_parent пересчитывает
        # родителя (проверяем лишь, что он действительно был пересчитан).
        close_oferta_on_zlecenie(self.oferta, self.user)
        self.main.refresh_from_db()
        self.assertIn(self.main.status, RequestStatus.values)

    def test_noop_when_already_done(self):
        self.oferta.status = Status.done
        self.oferta.save(update_fields=["status"])
        close_oferta_on_zlecenie(self.oferta, self.user)
        self.assertEqual(StatusHistory.objects.filter(request=self.main).count(), 0)


# ─────────────────────────── Task 11: admin actions ────────────────────────────

@override_settings(STORAGES=_SIMPLE_STATIC)
class ChildDocumentChainActionTests(TestCase):
    """POST-actions на карточках Oferta/Zlecenie: создают следующий документ."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(
            username="admin", email="a@a.com", password="x"
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.main = RequestMain.objects.create(**BASE_DATA, company_name="Zetom")
        self.oferta = Oferta.objects.create(
            **BASE_DATA, from_main=self.main, company_name="Zetom",
        )

    def test_zlecenie_action_sets_from_oferta_and_from_main(self):
        url = reverse("admin:zetom_oferta_zlecenie_action", args=[self.oferta.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        zlecenie = Zlecenie.objects.get(from_oferta=self.oferta)
        self.assertEqual(zlecenie.from_main, self.main)

    def test_zlecenie_action_closes_the_oferta(self):
        url = reverse("admin:zetom_oferta_zlecenie_action", args=[self.oferta.pk])
        self.client.post(url)
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.status, Status.done)

    def test_zlecenie_action_copies_contact_snapshot(self):
        self.oferta.first_name = "Jan"
        self.oferta.last_name = "Kowalski"
        self.oferta.company_nip = "7322215365"
        self.oferta.departments = [DepartmentsVariants.DEPARTMENT_1]
        self.oferta.save()

        url = reverse("admin:zetom_oferta_zlecenie_action", args=[self.oferta.pk])
        self.client.post(url)

        zlecenie = Zlecenie.objects.get(from_oferta=self.oferta)
        self.assertEqual(zlecenie.first_name, "Jan")
        self.assertEqual(zlecenie.last_name, "Kowalski")
        self.assertEqual(zlecenie.phone, self.oferta.phone)
        self.assertEqual(zlecenie.email, self.oferta.email)
        self.assertEqual(zlecenie.company_name, self.oferta.company_name)
        self.assertEqual(zlecenie.company_nip, self.oferta.company_nip)
        self.assertEqual(zlecenie.departments, self.oferta.departments)
        self.assertEqual(zlecenie.source, self.oferta.source)

    def test_wniosek_action_sets_from_zlecenie_and_does_not_close_it(self):
        zlecenie = Zlecenie.objects.create(**BASE_DATA, from_main=self.main)
        url = reverse("admin:zetom_zlecenie_wniosek_action", args=[zlecenie.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)

        wniosek = Wniosek.objects.get(from_zlecenie=zlecenie)
        self.assertEqual(wniosek.from_main, self.main)

        zlecenie.refresh_from_db()
        self.assertEqual(zlecenie.status, Status.new)

    @patch("crm.zetom.admin.children.user_has_perm")
    def test_zlecenie_action_requires_edit_permission(self, perm_mock):
        perm_mock.side_effect = lambda user, perm: perm != "edit_requests"
        url = reverse("admin:zetom_oferta_zlecenie_action", args=[self.oferta.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Zlecenie.objects.filter(from_oferta=self.oferta).count(), 0)

    def test_oferta_change_form_renders_the_chain_button(self):
        # claude — smoke test for the template button (Task 11 step 5).
        url = reverse("admin:zetom_oferta_change", args=[self.oferta.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("admin:zetom_oferta_zlecenie_action", args=[self.oferta.pk]),
        )

    def test_zlecenie_change_form_renders_the_chain_button(self):
        zlecenie = Zlecenie.objects.create(**BASE_DATA, from_main=self.main)
        url = reverse("admin:zetom_zlecenie_change", args=[zlecenie.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("admin:zetom_zlecenie_wniosek_action", args=[zlecenie.pk]),
        )
