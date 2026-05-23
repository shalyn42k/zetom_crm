# ──────────────────────────────────────────────────────────────────────────────
# ТЕСТЫ ВЬЮШЕК
#
# Что тут тестируется:
#   • GET /email/ — отдаёт страницу с формой (200)
#   • POST с валидными данными — создаёт RequestNull, отправляет уведомление, редирект (302)
#   • POST когда уведомление падает — RequestNull создаётся, страница ре-рендерится (200)
#   • POST с невалидными данными — RequestNull не создаётся, форма с ошибками (200)
#
# @patch — подменяет функцию на MagicMock на время одного теста.
#   Почему нужен: send_notification_to_staff реально отправляет email через SMTP.
#   В тестах нет SMTP-сервера → заменяем на заглушку.
#
# @override_settings — временно меняет настройки Django для одного теста/класса.
#   STATICFILES_STORAGE: ManifestStaticFilesStorage требует собранных статических
#   файлов (collectstatic). В тестах их нет → переключаем на простое хранилище.
# ──────────────────────────────────────────────────────────────────────────────

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from crm.notification.services.notification_service import (
    send_notification_to_staff,
)
from crm.zetom.models import RequestNull

# Валидные данные для AddRequestFormNull:
# first_name и last_name обязательны (установлено в форме через __init__).
VALID_POST = {
    "first_name": "Jan",
    "last_name": "Kowalski",
    "phone": "+48501600300",
    "email": "contact@zetom.pl",
}


@override_settings(
    # В Django 5.x статика настраивается через STORAGES["staticfiles"].
    # whitenoise.CompressedManifestStaticFilesStorage требует collectstatic
    # (создаёт staticfiles.json). В тестах его нет — заменяем на простое хранилище.
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class EmailTemplateViewTests(TestCase):
    url = reverse("zetom:index")

    @classmethod
    def setUpTestData(cls):
        # setUpTestData(): запускается ОДИН РАЗ для всего класса.
        # Создаёт суперюзера один раз и кэширует в cls.user — быстрее, чем setUp().
        # Нельзя изменять cls.user в тестах — он шарится между всеми методами.
        User = get_user_model()
        cls.user = User.objects.create_superuser(
            username="admin", email="a@a.com", password="x"
        )

    def setUp(self):
        # setUp(): запускается перед КАЖДЫМ тестом.
        # force_login() — авторизует пользователя без проверки пароля.
        # Шаблон расширяет Unfold admin base → требует аутентифицированной сессии.
        self.client.force_login(self.user)

    def test_get_returns_200_with_form_in_context(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Submit your request")
        # response.context — словарь контекста шаблона.
        # Проверяем что вьюшка передала форму в шаблон.
        self.assertIn("form", response.context)

    @patch("crm.zetom.views.send_notification_to_staff")
    def test_valid_post_saves_record_sends_notification_and_redirects(self, send_mock):
        # @patch заменяет send_notification_to_staff на MagicMock.
        # send_mock — это объект-заглушка. Можно проверить: был ли вызван, с какими аргументами.
        response = self.client.post(self.url, data=VALID_POST)

        # 302 = редирект → запись создана, всё хорошо
        self.assertEqual(response.status_code, 302)
        self.assertEqual(RequestNull.objects.count(), 1)
        new_obj = RequestNull.objects.first()

        # Уведомление должно быть отправлено с новым объектом
        send_mock.assert_called_once_with(new_obj)

        # Редирект ведёт в admin на страницу редактирования новой записи
        self.assertEqual(
            response["Location"],
            reverse("admin:zetom_requestnull_change", args=[new_obj.pk]),
        )

    @patch(
        "crm.zetom.views.send_notification_to_staff",
        side_effect=Exception("SMTP down"),  # мок бросает исключение
    )
    def test_notification_failure_still_saves_record_and_rerenders(self, _):
        # side_effect заставляет мок бросать Exception при вызове.
        # Вьюшка перехватывает его (except Exception) и делает re-render (200).
        # Запись при этом УЖЕ сохранена — commit=False был только до save().
        response = self.client.post(self.url, data=VALID_POST)
        self.assertEqual(response.status_code, 200)
        # Несмотря на падение уведомления — запись сохранена
        self.assertEqual(RequestNull.objects.count(), 1)

    def test_invalid_post_does_not_save_and_returns_errors(self):
        response = self.client.post(
            self.url,
            data={
                "first_name": "",   # обязательное
                "last_name": "",    # обязательное
                "phone": "abc",     # невалидный формат
                "email": "bad",     # невалидный email
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(RequestNull.objects.count(), 0)

        # response.context["form"] содержит форму с ошибками
        form = response.context["form"]
        self.assertFalse(form.is_valid())
        self.assertIn("phone", form.errors)
        self.assertIn("email", form.errors)


# ─────────────────── Интеграционный тест: реальная отправка email ──────────────

class NotificationServiceIntegrationTests(TestCase):
    """Тестируем сам сервис уведомлений — что email реально отправляется.

    @override_settings(EMAIL_BACKEND=...locmem...):
        locmem backend не делает настоящей SMTP-отправки — письма
        складываются в список mail.outbox. Это стандартный способ
        тестировать email в Django.

    Получателей резолвит services/recipients.dep_heads_or_admins_emails:
    он ищет активных юзеров с role.code == "department_head", иначе fallback
    на role.code == "admin". Поэтому в setUpTestData мы заводим одного
    admin'а с валидным email — иначе письмо никому не уйдёт.
    """

    @classmethod
    def setUpTestData(cls):
        # UserProfile создаётся автоматически через post_save сигнал
        # (crm/users/signals_profile.py). Здесь только подменяем role на admin.
        from crm.users.models import Role

        User = get_user_model()
        cls.admin_user = User.objects.create_user(
            username="staff_admin",
            email="staff_admin@zetom.test",
            password="x",
        )
        admin_role, _ = Role.objects.get_or_create(
            code="admin", defaults={"name": "Administrator"}
        )
        cls.admin_user.profile.role = admin_role
        cls.admin_user.profile.save(update_fields=["role"])

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_send_notification_creates_email_in_outbox(self):
        obj = RequestNull.objects.create(
            phone="+48501600300",
            email="contact@zetom.pl",
            company_name="Zetom Sp. z o.o.",
        )
        send_notification_to_staff(obj)

        # mail.outbox — список отправленных писем (только с locmem backend)
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        # Тема письма должна содержать ID и название компании
        self.assertIn(str(obj.id), msg.subject)
        self.assertIn(obj.company_name, msg.subject)
        # И уйти на адрес admin'а из setUpTestData (а не на захардкоженный).
        self.assertEqual(msg.to, [self.admin_user.email])
