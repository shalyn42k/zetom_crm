# ──────────────────────────────────────────────────────────────────────────────
# ТЕСТЫ ADMIN
#
# Что тут тестируется:
#   • approve_action (RequestNull → RequestMain + уведомление)
#   • oferta/zlecenie/wniosek actions (создание дочерних документов)
#   • apply_status_action (смена статуса с/без reason)
#   • ChildSaveModelTests (save_model через admin change-форму)
#
# Почему @patch("crm.zetom.admin.base.user_has_perm"):
#   BaseRequestAdmin.has_*_permission() вызывает user_has_perm() из base.py.
#   Супер-юзер проходит is_superuser=True → True, но user_has_perm делает
#   дополнительные проверки profile/role. Патчим в точке ИСПОЛЬЗОВАНИЯ (base.py).
#
# @override_settings(STATICFILES_STORAGE=...):
#   Unfold шаблоны используют {% static %} с ManifestStaticFilesStorage,
#   которому нужен staticfiles.json от collectstatic. В тестах его нет.
# ──────────────────────────────────────────────────────────────────────────────

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from crm.status_manager.services.statuses import RequestStatus, Status
from crm.zetom.models import Oferta, RequestMain, RequestNull, Wniosek, Zlecenie

BASE_DATA = {
    "phone": "+48501600300",
    "email": "contact@zetom.pl",
}


def always_true(*args, **kwargs):
    """Заглушка для user_has_perm — всегда возвращает True."""
    return True


# ─────────────────────────── RequestNull approve ──────────────────────────────

_SIMPLE_STATIC = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(STORAGES=_SIMPLE_STATIC)
@patch("crm.zetom.admin.base.user_has_perm", side_effect=always_true)
class ApproveNullAdminActionTests(TestCase):
    """Тест кнопки «Approve» на странице RequestNull в admins.

    Кнопка вызывает approve_action, который:
    1. Создаёт RequestMain из данных RequestNull
    2. Отправляет уведомление
    3. Редиректит на страницу нового RequestMain
    """

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_superuser(
            username="admin", email="a@a.com", password="x"
        )

    def setUp(self):
        self.client.force_login(self.user)

    @patch("crm.zetom.admin.requestnull.send_notification_approve_null")
    def test_approve_creates_main_sends_notification_and_redirects(
        self, send_mock, _perm_mock
    ):
        # Обрати внимание на порядок аргументов: сначала идут патчи снизу вверх.
        # @patch на методе (send_mock) → первый аргумент после self.
        # @patch на классе (_perm_mock) → второй аргумент.
        null = RequestNull.objects.create(**BASE_DATA)
        url = reverse("admin:zetom_requestnull_approve_action", args=[null.pk])

        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(RequestMain.objects.count(), 1)
        main = RequestMain.objects.first()
        self.assertEqual(main.email, null.email)
        send_mock.assert_called_once_with(main)


# ─────────────────────────── RequestMain actions ──────────────────────────────

@override_settings(STORAGES=_SIMPLE_STATIC)
@patch("crm.zetom.admin.base.user_has_perm", side_effect=always_true)
class MainAdminActionTests(TestCase):
    """Кастомные действия на странице RequestMain.

    oferta/zlecenie/wniosek action — создают дочерние документы.
    apply_status_action — меняет статус заявки (с логикой reason для cancelled/deleted).
    """

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_superuser(
            username="admin", email="a@a.com", password="x"
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.main = RequestMain.objects.create(**BASE_DATA)

    def test_oferta_action_creates_oferta_and_redirects(self, _):
        url = reverse("admin:zetom_requestmain_oferta_action", args=[self.main.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Oferta.objects.filter(from_main=self.main).count(), 1)

    def test_zlecenie_action_creates_zlecenie_and_redirects(self, _):
        url = reverse("admin:zetom_requestmain_zlecenie_action", args=[self.main.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Zlecenie.objects.filter(from_main=self.main).count(), 1)

    def test_wniosek_action_creates_wniosek_and_redirects(self, _):
        url = reverse("admin:zetom_requestmain_wniosek_action", args=[self.main.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Wniosek.objects.filter(from_main=self.main).count(), 1)

    def test_apply_status_open_changes_status(self, _):
        # active → open — допустимый переход без reason
        url = reverse("admin:zetom_requestmain_apply_status", args=[self.main.pk])
        response = self.client.post(url, data={"new_status": RequestStatus.open})
        self.assertEqual(response.status_code, 302)
        self.main.refresh_from_db()
        self.assertEqual(self.main.status, RequestStatus.open)

    def test_apply_same_status_keeps_status_unchanged(self, _):
        # active → active = ValueError → messages.error → редирект без изменений
        url = reverse("admin:zetom_requestmain_apply_status", args=[self.main.pk])
        response = self.client.post(url, data={"new_status": RequestStatus.active})
        self.assertEqual(response.status_code, 302)
        self.main.refresh_from_db()
        self.assertEqual(self.main.status, RequestStatus.active)

    def test_apply_cancelled_without_reason_renders_reason_form(self, _):
        # cancelled требует reason → ReasonRequired → рендерит форму для ввода причины.
        # Это паттерн «попросить доп. данные» вместо немедленного действия.
        url = reverse("admin:zetom_requestmain_apply_status", args=[self.main.pk])
        response = self.client.post(url, data={"new_status": RequestStatus.cancelled})
        # 200 = рендер формы reason (не редирект)
        self.assertEqual(response.status_code, 200)
        self.assertIn("form", response.context)

    def test_apply_cancelled_with_reason_changes_status(self, _):
        url = reverse("admin:zetom_requestmain_apply_status", args=[self.main.pk])
        response = self.client.post(
            url, data={"new_status": RequestStatus.cancelled, "reason": "client request"}
        )
        self.assertEqual(response.status_code, 302)
        self.main.refresh_from_db()
        self.assertEqual(self.main.status, RequestStatus.cancelled)


# ─────────────────────────── ChildSaveModel (Oferta) ──────────────────────────

@override_settings(STORAGES=_SIMPLE_STATIC)
@patch("crm.zetom.admin.base.user_has_perm", side_effect=always_true)
class ChildSaveModelTests(TestCase):
    """OfertaAdmin.save_model делегирует в save_child_with_status.

    Тестируем через POST на admin change-форму:
    - Допустимый переход статуса → объект сохраняется (302)
    - Недопустимый переход → статус не меняется, но ответ всё равно 302
      (admin перенаправляет, ошибка показывается через messages)
    """

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_superuser(
            username="admin", email="a@a.com", password="x"
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.main = RequestMain.objects.create(**BASE_DATA)
        self.oferta = Oferta.objects.create(**BASE_DATA, from_main=self.main)

    def _change_url(self):
        return reverse("admin:zetom_oferta_change", args=[self.oferta.pk])

    def _form_data(self, status):
        # Все обязательные поля admin-формы Oferta.
        # departments — пустой список (не обязательное).
        return {
            **BASE_DATA,
            "company_nip": "7322215365",
            "status": status,
            "price": "0",
            "notes": "",
            "source": "other",
            "departments": [],
        }

    def test_valid_transition_saved(self, _):
        response = self.client.post(self._change_url(), data=self._form_data(Status.in_progress))
        # 302 — сохранилось и редиректнуло; 200 — форма с ошибками (оба валидны в тесте)
        self.assertIn(response.status_code, (302, 200))
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.status, Status.in_progress)

    def test_invalid_transition_does_not_change_status(self, _):
        # new → waiting недопустимо. save_child_with_status возвращает False,
        # super().save_model() не вызывается → статус остаётся new.
        self.client.post(self._change_url(), data=self._form_data(Status.waiting))
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.status, Status.new)
