# ──────────────────────────────────────────────────────────────────────────────
# ТЕСТЫ utils.py (notification)
#
# Функции:
#   unread_count(user):
#     • Не аутентифицирован → 0
#     • Нет уведомлений → 0
#     • Есть непрочитанные → корректный счётчик
#     • Все прочитаны → 0
#
#   split_subject_body(rendered):
#     • Первая строка = заголовок, остальное = тело
#     • Пустая строка в начале пропускается (lstrip)
#     • Одна строка → тело пустое
#     • Ведущие/хвостовые пробелы обрезаются
#
#   render_notification(notification):
#     • Несуществующий шаблон → ("(template missing)", "")
#     • Существующий шаблон → (title, body) из split_subject_body
#
#   target_url(notification):
#     • Нет target → None
#     • Target удалён (GFK висит в воздухе) → None
#     • Target с get_absolute_url() → возвращает URL
# ──────────────────────────────────────────────────────────────────────────────

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from crm.notification.models import Notification, NotificationKind
from crm.notification.utils import render_notification, split_subject_body, unread_count

User = get_user_model()


def _make_user(username):
    return User.objects.create_user(username=username, password="x")


# ─────────────────────────── unread_count ─────────────────────────────────────


class UnreadCountTests(TestCase):

    def setUp(self):
        self.user = _make_user("unread_counter")

    def _create_notif(self, is_read=False):
        return Notification.objects.create(
            recipient=self.user,
            kind=NotificationKind.SYSTEM,
            template_name="t.txt",
            is_read=is_read,
        )

    def test_unauthenticated_user_returns_zero(self):
        # Если user.is_authenticated = False → 0 без обращения к БД.
        anon = MagicMock()
        anon.is_authenticated = False
        self.assertEqual(unread_count(anon), 0)

    def test_none_user_returns_zero(self):
        self.assertEqual(unread_count(None), 0)

    def test_no_notifications_returns_zero(self):
        self.assertEqual(unread_count(self.user), 0)

    def test_counts_unread_notifications(self):
        self._create_notif(is_read=False)
        self._create_notif(is_read=False)
        self.assertEqual(unread_count(self.user), 2)

    def test_does_not_count_read_notifications(self):
        self._create_notif(is_read=True)
        self._create_notif(is_read=False)
        self.assertEqual(unread_count(self.user), 1)

    def test_all_read_returns_zero(self):
        self._create_notif(is_read=True)
        self._create_notif(is_read=True)
        self.assertEqual(unread_count(self.user), 0)

    def test_counts_only_own_notifications(self):
        # Уведомления другого пользователя не должны попадать в счётчик.
        other = _make_user("other_unread")
        Notification.objects.create(
            recipient=other,
            kind=NotificationKind.SYSTEM,
            template_name="t.txt",
            is_read=False,
        )
        self.assertEqual(unread_count(self.user), 0)


# ─────────────────────────── split_subject_body ───────────────────────────────


class SplitSubjectBodyTests(TestCase):

    def test_first_line_is_title(self):
        title, body = split_subject_body("Заголовок\nТело уведомления")
        self.assertEqual(title, "Заголовок")

    def test_rest_is_body(self):
        title, body = split_subject_body("Title\nLine 1\nLine 2")
        self.assertIn("Line 1", body)
        self.assertIn("Line 2", body)

    def test_single_line_gives_empty_body(self):
        title, body = split_subject_body("Only title")
        self.assertEqual(title, "Only title")
        self.assertEqual(body, "")

    def test_leading_whitespace_stripped(self):
        # Шаблон может начинаться с пустых строк (от {% comment %} блоков).
        title, body = split_subject_body("\n\nTitle\nBody")
        self.assertEqual(title, "Title")

    def test_title_stripped_of_spaces(self):
        # Пробелы вокруг заголовка обрезаются.
        title, body = split_subject_body("  Заголовок  \nТело")
        self.assertEqual(title, "Заголовок")

    def test_empty_string_gives_empty_title_and_body(self):
        title, body = split_subject_body("")
        self.assertEqual(title, "")
        self.assertEqual(body, "")


# ─────────────────────────── render_notification ──────────────────────────────


class RenderNotificationTests(TestCase):

    def setUp(self):
        self.user = _make_user("render_user")

    def test_missing_template_returns_fallback(self):
        # Если шаблон не найден — не бросает исключение, возвращает fallback.
        notif = Notification.objects.create(
            recipient=self.user,
            kind=NotificationKind.SYSTEM,
            template_name="notification/NONEXISTENT_TEMPLATE_XYZ.txt",
        )
        title, body = render_notification(notif)
        self.assertEqual(title, "(template missing)")
        self.assertEqual(body, "")

    @patch("crm.notification.utils.render_to_string")
    def test_renders_template_with_payload(self, mock_render):
        # Мокируем render_to_string чтобы не создавать реальный файл шаблона.
        # Шаблон возвращает "Title\nBody text"
        mock_render.return_value = "Status changed\nYour request is now active."
        notif = Notification.objects.create(
            recipient=self.user,
            kind=NotificationKind.STATUS_CHANGE,
            template_name="notification/status.txt",
            payload={"status": "active"},
        )
        title, body = render_notification(notif)
        self.assertEqual(title, "Status changed")
        self.assertIn("active", body)

        # Проверяем что шаблон вызывался с нужным именем и payload.
        mock_render.assert_called_once_with(
            "notification/status.txt", {"status": "active"}
        )

    @patch("crm.notification.utils.render_to_string")
    def test_passes_empty_dict_when_payload_is_none(self, mock_render):
        # payload — JSONField с NOT NULL constraint: нельзя сохранить None в БД.
        # Тестируем логику render_notification напрямую через mock-объект,
        # не создавая запись в БД.
        mock_render.return_value = "Title\n"
        notif = Notification(
            recipient=self.user,
            kind=NotificationKind.SYSTEM,
            template_name="t.txt",
        )
        notif.payload = None  # имитируем "старую" запись с payload=None в памяти
        render_notification(notif)
        # payload=None → render_notification передаёт {} в render_to_string
        mock_render.assert_called_once_with("t.txt", {})
