# ──────────────────────────────────────────────────────────────────────────────
# ТЕСТЫ МОДЕЛЕЙ notification
#
# EmailNotification:
#   • Поля сохраняются (recipient_email, subject, status, payload)
#   • Статус по умолчанию = PENDING
#   • __str__ показывает статус, тему, адрес
#   • actor — FK nullable (SET_NULL при удалении User)
#
# Notification (inapp):
#   • Поля сохраняются (recipient, kind, template_name, payload)
#   • is_read по умолчанию = False
#   • read_at по умолчанию = None
#   • __str__ показывает kind и участников
#   • Каскадное удаление при удалении recipient (CASCADE)
#   • actor → SET_NULL при удалении actor-пользователя
# ──────────────────────────────────────────────────────────────────────────────

from django.contrib.auth import get_user_model
from django.test import TestCase

from crm.notification.models import (
    EmailNotification,
    EmailStatus,
    Notification,
    NotificationKind,
)

User = get_user_model()


# ─────────────────────────── EmailNotification ────────────────────────────────


class EmailNotificationModelTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username="actor_en", password="x")

    def test_create_persists_required_fields(self):
        obj = EmailNotification.objects.create(
            recipient_email="client@test.com",
            subject="Test subject",
            template_name="notification/email_test.txt",
        )
        obj.refresh_from_db()
        self.assertEqual(obj.recipient_email, "client@test.com")
        self.assertEqual(obj.subject, "Test subject")

    def test_default_status_is_pending(self):
        # Новое письмо всегда начинается в PENDING — аудит-лог фиксирует это.
        obj = EmailNotification.objects.create(
            recipient_email="test@test.com",
            subject="Hi",
            template_name="t.txt",
        )
        obj.refresh_from_db()
        self.assertEqual(obj.status, EmailStatus.PENDING)

    def test_payload_default_is_empty_dict(self):
        obj = EmailNotification.objects.create(
            recipient_email="test@test.com",
            subject="Hi",
            template_name="t.txt",
        )
        obj.refresh_from_db()
        self.assertEqual(obj.payload, {})

    def test_actor_nullable(self):
        # actor — nullable FK. Системные письма отправляются без актора.
        obj = EmailNotification.objects.create(
            recipient_email="test@test.com",
            subject="System",
            template_name="t.txt",
        )
        obj.refresh_from_db()
        self.assertIsNone(obj.actor)

    def test_actor_set_null_on_user_delete(self):
        # on_delete=SET_NULL: удаление User-а обнуляет actor в EmailNotification.
        obj = EmailNotification.objects.create(
            recipient_email="test@test.com",
            subject="From actor",
            template_name="t.txt",
            actor=self.user,
        )
        self.user.delete()
        obj.refresh_from_db()
        self.assertIsNone(obj.actor)

    def test_str_contains_status_subject_and_email(self):
        obj = EmailNotification.objects.create(
            recipient_email="check@test.com",
            subject="Check this",
            template_name="t.txt",
            status=EmailStatus.SENT,
        )
        result = str(obj)
        self.assertIn("SENT", result)
        self.assertIn("Check this", result)
        self.assertIn("check@test.com", result)

    def test_status_reason_nullable(self):
        obj = EmailNotification.objects.create(
            recipient_email="test@test.com",
            subject="x",
            template_name="t.txt",
        )
        obj.refresh_from_db()
        self.assertIsNone(obj.status_reason)

    def test_sent_at_nullable(self):
        obj = EmailNotification.objects.create(
            recipient_email="test@test.com",
            subject="x",
            template_name="t.txt",
        )
        obj.refresh_from_db()
        self.assertIsNone(obj.sent_at)


# ─────────────────────────── Notification (inapp) ─────────────────────────────


class NotificationModelTests(TestCase):

    def setUp(self):
        self.recipient = User.objects.create_user(username="recipient_n", password="x")
        self.actor = User.objects.create_user(username="actor_n", password="x")

    def test_create_persists_required_fields(self):
        obj = Notification.objects.create(
            recipient=self.recipient,
            kind=NotificationKind.SYSTEM,
            template_name="notification/system.txt",
        )
        obj.refresh_from_db()
        self.assertEqual(obj.recipient, self.recipient)
        self.assertEqual(obj.kind, NotificationKind.SYSTEM)

    def test_is_read_default_false(self):
        # Новое уведомление всегда непрочитанное.
        obj = Notification.objects.create(
            recipient=self.recipient,
            kind=NotificationKind.SYSTEM,
            template_name="t.txt",
        )
        obj.refresh_from_db()
        self.assertFalse(obj.is_read)

    def test_read_at_default_none(self):
        obj = Notification.objects.create(
            recipient=self.recipient,
            kind=NotificationKind.SYSTEM,
            template_name="t.txt",
        )
        obj.refresh_from_db()
        self.assertIsNone(obj.read_at)

    def test_payload_default_is_empty_dict(self):
        obj = Notification.objects.create(
            recipient=self.recipient,
            kind=NotificationKind.ASSIGNMENT,
            template_name="t.txt",
        )
        obj.refresh_from_db()
        self.assertEqual(obj.payload, {})

    def test_actor_nullable(self):
        # Системные уведомления не имеют актора.
        obj = Notification.objects.create(
            recipient=self.recipient,
            kind=NotificationKind.SYSTEM,
            template_name="t.txt",
        )
        obj.refresh_from_db()
        self.assertIsNone(obj.actor)

    def test_actor_set_null_on_actor_user_delete(self):
        # Удаление actor-пользователя → actor в Notification = NULL (SET_NULL).
        obj = Notification.objects.create(
            recipient=self.recipient,
            actor=self.actor,
            kind=NotificationKind.STATUS_CHANGE,
            template_name="t.txt",
        )
        self.actor.delete()
        obj.refresh_from_db()
        self.assertIsNone(obj.actor)

    def test_notification_deleted_on_recipient_delete(self):
        # on_delete=CASCADE: удаление recipient удаляет его уведомления.
        obj = Notification.objects.create(
            recipient=self.recipient,
            kind=NotificationKind.SYSTEM,
            template_name="t.txt",
        )
        pk = obj.pk
        self.recipient.delete()
        self.assertFalse(Notification.objects.filter(pk=pk).exists())

    def test_str_contains_kind_and_usernames(self):
        obj = Notification.objects.create(
            recipient=self.recipient,
            actor=self.actor,
            kind=NotificationKind.STATUS_CHANGE,
            template_name="t.txt",
        )
        result = str(obj)
        # __str__ строит "kind_label · actor → recipient · when"
        self.assertIn(self.recipient.username, result)
        self.assertIn(self.actor.username, result)

    def test_str_shows_system_when_no_actor(self):
        obj = Notification.objects.create(
            recipient=self.recipient,
            kind=NotificationKind.SYSTEM,
            template_name="t.txt",
        )
        result = str(obj)
        self.assertIn("system", result)
