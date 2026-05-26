# ──────────────────────────────────────────────────────────────────────────────
# ТЕСТЫ ВЬЮШЕК notification
#
# Views:
#   inbox(request)          — GET /notifications/
#   mark_read(request, pk)  — POST /notifications/<pk>/read/
#   mark_all_read(request)  — POST /notifications/read-all/
#
# Особенности:
#   • inbox() защищён @staff_member_required — нужен is_staff=True
#   • mark_read() / mark_all_read() защищены @login_required
#   • mark_read() проверяет notification.recipient == request.user
#     (иначе 403 Forbidden)
#   • render_notification() рендерит шаблоны — мокируем через patch,
#     чтобы не создавать реальных файлов шаблонов
# ──────────────────────────────────────────────────────────────────────────────

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from crm.notification.models import Notification, NotificationKind

User = get_user_model()


def _make_staff(username, email=None):
    """Создаёт is_staff=True пользователя (нужен для inbox)."""
    return User.objects.create_user(
        username=username,
        email=email or f"{username}@test.com",
        password="x",
        is_staff=True,
    )


def _make_user(username):
    return User.objects.create_user(username=username, password="x")


def _create_notif(recipient, kind=NotificationKind.SYSTEM, is_read=False):
    return Notification.objects.create(
        recipient=recipient,
        kind=kind,
        template_name="t.txt",
        is_read=is_read,
    )


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class InboxViewTests(TestCase):
    """inbox() — страница входящих уведомлений."""

    @classmethod
    def setUpTestData(cls):
        cls.staff_user = _make_staff("inbox_staff")

    def setUp(self):
        self.client.force_login(self.staff_user)

    @patch("crm.notification.views.render_notification", return_value=("Title", "Body"))
    def test_inbox_returns_200(self, _mock):
        response = self.client.get(reverse("notification:inbox"))
        self.assertEqual(response.status_code, 200)

    def test_inbox_redirects_anonymous_user(self):
        # @staff_member_required → неавторизованный → редирект на логин.
        self.client.logout()
        response = self.client.get(reverse("notification:inbox"))
        self.assertEqual(response.status_code, 302)

    def test_inbox_403_for_non_staff(self):
        # is_staff=False → @staff_member_required → редирект (не 200).
        non_staff = _make_user("non_staff_inbox")
        self.client.force_login(non_staff)
        response = self.client.get(reverse("notification:inbox"))
        self.assertNotEqual(response.status_code, 200)

    @patch("crm.notification.views.render_notification", return_value=("Title", "Body"))
    def test_inbox_filter_all_includes_read_and_unread(self, _mock):
        _create_notif(self.staff_user, is_read=True)
        _create_notif(self.staff_user, is_read=False)
        response = self.client.get(reverse("notification:inbox") + "?filter=all")
        self.assertEqual(response.status_code, 200)
        # Оба уведомления должны попасть в items.
        self.assertEqual(len(response.context["items"]), 2)

    @patch("crm.notification.views.render_notification", return_value=("Title", "Body"))
    def test_inbox_filter_unread_shows_only_unread(self, _mock):
        _create_notif(self.staff_user, is_read=True)
        _create_notif(self.staff_user, is_read=False)
        response = self.client.get(reverse("notification:inbox") + "?filter=unread")
        self.assertEqual(response.status_code, 200)
        items = response.context["items"]
        # Все записи в items должны быть непрочитанными.
        self.assertTrue(all(not item["is_read"] for item in items))

    @patch("crm.notification.views.render_notification", return_value=("Title", "Body"))
    def test_inbox_kind_filter_shows_only_matching_kind(self, _mock):
        _create_notif(self.staff_user, kind=NotificationKind.SYSTEM)
        _create_notif(self.staff_user, kind=NotificationKind.ASSIGNMENT)
        response = self.client.get(
            reverse("notification:inbox") + f"?kind={NotificationKind.SYSTEM}"
        )
        items = response.context["items"]
        self.assertTrue(all(item["kind"] == NotificationKind.SYSTEM for item in items))

    @patch("crm.notification.views.render_notification", return_value=("Title", "Body"))
    def test_inbox_invalid_filter_defaults_to_all(self, _mock):
        # Неизвестное значение filter= → игнорируется, показывается "all".
        _create_notif(self.staff_user)
        response = self.client.get(reverse("notification:inbox") + "?filter=garbage")
        self.assertEqual(response.context["filter_value"], "all")

    @patch("crm.notification.views.render_notification", return_value=("Title", "Body"))
    def test_inbox_context_has_counts(self, _mock):
        _create_notif(self.staff_user, is_read=False)
        response = self.client.get(reverse("notification:inbox"))
        # total_count и unread_count_total должны присутствовать в контексте.
        self.assertIn("total_count", response.context)
        self.assertIn("unread_count_total", response.context)
        self.assertEqual(response.context["total_count"], 1)
        self.assertEqual(response.context["unread_count_total"], 1)

    @patch("crm.notification.views.render_notification", return_value=("Title", "Body"))
    def test_inbox_shows_only_own_notifications(self, _mock):
        other = _make_staff("other_inbox_staff")
        _create_notif(other)
        response = self.client.get(reverse("notification:inbox"))
        # Уведомление другого пользователя не должно появляться.
        self.assertEqual(len(response.context["items"]), 0)


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class MarkReadViewTests(TestCase):
    """mark_read() — POST /notifications/<pk>/read/"""

    def setUp(self):
        self.user = _make_user("mark_read_user")
        self.other = _make_user("mark_read_other")
        self.notif = _create_notif(self.user)
        self.client.force_login(self.user)

    def test_mark_read_redirects_to_inbox(self):
        # После пометки → редирект (302).
        response = self.client.post(reverse("notification:mark_read", args=[self.notif.pk]))
        self.assertEqual(response.status_code, 302)

    def test_mark_read_sets_is_read_true(self):
        self.client.post(reverse("notification:mark_read", args=[self.notif.pk]))
        self.notif.refresh_from_db()
        self.assertTrue(self.notif.is_read)

    def test_mark_read_returns_403_for_wrong_user(self):
        # Другой пользователь пытается прочитать чужое уведомление.
        self.client.force_login(self.other)
        response = self.client.post(reverse("notification:mark_read", args=[self.notif.pk]))
        self.assertEqual(response.status_code, 403)

    def test_mark_read_wrong_user_does_not_change_is_read(self):
        self.client.force_login(self.other)
        self.client.post(reverse("notification:mark_read", args=[self.notif.pk]))
        self.notif.refresh_from_db()
        self.assertFalse(self.notif.is_read)

    def test_mark_read_404_for_nonexistent(self):
        response = self.client.post(reverse("notification:mark_read", args=[999999]))
        self.assertEqual(response.status_code, 404)

    def test_mark_read_requires_post(self):
        # GET на mark_read → 405 Method Not Allowed (@require_POST).
        response = self.client.get(reverse("notification:mark_read", args=[self.notif.pk]))
        self.assertEqual(response.status_code, 405)

    def test_mark_read_anonymous_redirects(self):
        # @login_required → анонимный → редирект на логин.
        self.client.logout()
        response = self.client.post(reverse("notification:mark_read", args=[self.notif.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response["Location"])

    def test_mark_read_with_back_param_redirects_there(self):
        # ?back=/admin/ → редирект на /admin/ (same-origin path).
        response = self.client.post(
            reverse("notification:mark_read", args=[self.notif.pk]) + "?back=/admin/"
        )
        self.assertRedirects(response, "/admin/", fetch_redirect_response=False)

    def test_mark_read_back_param_must_start_with_slash(self):
        # back=http://evil.com → игнорируется (безопасность: только local paths).
        response = self.client.post(
            reverse("notification:mark_read", args=[self.notif.pk]) + "?back=http://evil.com/hack"
        )
        # Редирект должен быть на inbox, не на внешний URL.
        self.assertNotIn("evil.com", response.get("Location", ""))


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class MarkAllReadViewTests(TestCase):
    """mark_all_read() — POST /notifications/read-all/"""

    def setUp(self):
        self.user = _make_user("mark_all_user")
        self.client.force_login(self.user)

    def test_mark_all_read_redirects_to_inbox(self):
        # fetch_redirect_response=False — не пытаемся открыть страницу после редиректа.
        # Inbox требует is_staff=True, а тестовый пользователь обычный.
        response = self.client.post(reverse("notification:mark_all_read"))
        self.assertRedirects(
            response, reverse("notification:inbox"), fetch_redirect_response=False
        )

    def test_mark_all_read_marks_all_unread(self):
        _create_notif(self.user, is_read=False)
        _create_notif(self.user, is_read=False)
        self.client.post(reverse("notification:mark_all_read"))
        unread_count = Notification.objects.filter(
            recipient=self.user, is_read=False
        ).count()
        self.assertEqual(unread_count, 0)

    def test_mark_all_read_requires_post(self):
        response = self.client.get(reverse("notification:mark_all_read"))
        self.assertEqual(response.status_code, 405)

    def test_mark_all_read_anonymous_redirects(self):
        self.client.logout()
        response = self.client.post(reverse("notification:mark_all_read"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response["Location"])

    def test_mark_all_read_does_not_affect_other_users(self):
        other = _make_user("other_mark_all")
        other_notif = _create_notif(other, is_read=False)
        self.client.post(reverse("notification:mark_all_read"))
        other_notif.refresh_from_db()
        self.assertFalse(other_notif.is_read)
