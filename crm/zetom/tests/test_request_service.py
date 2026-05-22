# ──────────────────────────────────────────────────────────────────────────────
# ТЕСТЫ request_service
#
# approve_null_action  — превращает RequestNull в RequestMain (одобрение)
# approve_*_action     — создаёт дочерний документ к RequestMain
#
# Что важно проверить:
#   • Данные копируются из родителя в дочерний объект
#   • RequestNull скрывается после approve (мягкое удаление)
#   • Http404 бросается при несуществующем pk
#   • Назначенные пользователи (assigned_to) копируются в дочерний документ
# ──────────────────────────────────────────────────────────────────────────────

from django.contrib.auth import get_user_model
from django.http import Http404
from django.test import TestCase

from crm.status_manager.services.statuses import Status
from crm.zetom.models import Oferta, RequestMain, RequestNull, Wniosek, Zlecenie
from crm.zetom.services.request_service import (
    approve_null_action,
    approve_oferta_action,
    approve_wniosek_action,
    approve_zlecenie_action,
)

User = get_user_model()

BASE_DATA = {
    "phone": "+48501600300",
    "email": "contact@zetom.pl",
}


# ─────────────────────────── approve_null_action ──────────────────────────────

class ApproveNullActionTests(TestCase):
    """Одобрение первичной заявки: RequestNull → RequestMain.

    Внутри используется update_or_create по from_null, поэтому повторный
    вызов с тем же null обновит существующий RequestMain, а не создаст второй.
    """

    def test_creates_requestmain_with_copied_fields(self):
        null = RequestNull.objects.create(
            **BASE_DATA,
            company_name="Zetom Sp. z o.o.",
            message="Interesuje nas kalibracja",
        )
        main = approve_null_action(null.pk)

        self.assertIsInstance(main, RequestMain)
        self.assertEqual(main.email, null.email)
        self.assertEqual(main.company_name, null.company_name)
        self.assertEqual(main.message, "Interesuje nas kalibracja")

    def test_soft_deletes_null_after_approval(self):
        # После одобрения RequestNull скрывается через safedelete
        # (мягкое удаление — из стандартного менеджера не виден).
        null = RequestNull.objects.create(**BASE_DATA)
        approve_null_action(null.pk)
        self.assertFalse(RequestNull.objects.filter(pk=null.pk).exists())

    def test_null_still_in_db_after_soft_delete(self):
        # all_with_deleted() — менеджер safedelete — видит мягко-удалённые.
        null = RequestNull.objects.create(**BASE_DATA)
        approve_null_action(null.pk)
        self.assertTrue(
            RequestNull.objects.all_with_deleted().filter(pk=null.pk).exists()
        )

    def test_two_different_nulls_create_two_mains(self):
        # У каждого null свой from_null ключ → два разных RequestMain.
        null1 = RequestNull.objects.create(**BASE_DATA, company_name="Alpha")
        null2 = RequestNull.objects.create(**BASE_DATA, company_name="Beta")
        approve_null_action(null1.pk)
        approve_null_action(null2.pk)
        self.assertEqual(RequestMain.objects.count(), 2)

    def test_raises_404_for_nonexistent_null_pk(self):
        # get_object_or_404 бросает Http404, если запись не найдена.
        with self.assertRaises(Http404):
            approve_null_action(999999)


# ─────────────────────────── approve_*_action ─────────────────────────────────

class ApproveChildActionTests(TestCase):
    """Создание дочерних документов (Oferta, Zlecenie, Wniosek) из RequestMain."""

    def setUp(self):
        self.main = RequestMain.objects.create(**BASE_DATA, company_name="Zetom")

    def test_approve_oferta_creates_linked_oferta(self):
        oferta = approve_oferta_action(self.main.pk)
        self.assertIsInstance(oferta, Oferta)
        self.assertEqual(oferta.from_main, self.main)

    def test_approve_oferta_sets_price_zero(self):
        # Начальная цена 0 — менеджер потом уточняет через форму.
        oferta = approve_oferta_action(self.main.pk)
        self.assertEqual(oferta.price, 0)

    def test_approve_oferta_default_status_is_new(self):
        oferta = approve_oferta_action(self.main.pk)
        self.assertEqual(oferta.status, Status.new)

    def test_approve_zlecenie_creates_linked_zlecenie(self):
        zlec = approve_zlecenie_action(self.main.pk)
        self.assertIsInstance(zlec, Zlecenie)
        self.assertEqual(zlec.from_main, self.main)
        self.assertEqual(zlec.price, 0)

    def test_approve_wniosek_creates_linked_wniosek(self):
        wn = approve_wniosek_action(self.main.pk)
        self.assertIsInstance(wn, Wniosek)
        self.assertEqual(wn.from_main, self.main)

    def test_child_inherits_assigned_users_from_main(self):
        # _approve_child копирует assigned_to из main через child.assigned_to.set(...)
        user = User.objects.create_user(username="worker", password="x")
        self.main.assigned_to.add(user)
        oferta = approve_oferta_action(self.main.pk)
        self.assertIn(user, oferta.assigned_to.all())

    def test_child_does_not_inherit_unrelated_users(self):
        # Пользователи, которых нет в main.assigned_to, не попадают в дочерний.
        user_on_main = User.objects.create_user(username="worker1", password="x")
        user_other = User.objects.create_user(username="worker2", password="x")
        self.main.assigned_to.add(user_on_main)
        oferta = approve_oferta_action(self.main.pk)
        self.assertNotIn(user_other, oferta.assigned_to.all())

    def test_raises_404_for_missing_main(self):
        for fn in (approve_oferta_action, approve_zlecenie_action, approve_wniosek_action):
            with self.subTest(fn=fn.__name__):
                # subTest: даже если один падает, остальные продолжают выполняться
                with self.assertRaises(Http404):
                    fn(999999)
