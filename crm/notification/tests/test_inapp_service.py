# ──────────────────────────────────────────────────────────────────────────────
# ТЕСТЫ inapp_service.py
#
# Функции:
#   create_inapp() — создаёт Notification для каждого получателя
#   mark_read()    — помечает одно уведомление прочитанным (идемпотентно)
#   mark_all_read() — помечает все непрочитанные уведомления юзера
#
# Тест-кейсы:
#   create_inapp:
#     • Нет получателей → возвращает [] и ничего не создаёт в БД
#     • Один получатель → создаёт одну запись
#     • Несколько получателей → по одной записи на каждого
#     • Неизвестный kind → дефолтится в SYSTEM
#     • С actor и target → поля заполнены
#   mark_read:
#     • Непрочитанное → is_read=True, read_at заполнен, возвращает True
#     • Уже прочитанное → ничего не меняет, возвращает False (идемпотентность)
#     • Чужое уведомление → возвращает False, не меняет
#   mark_all_read:
#     • Помечает только непрочитанные текущего юзера
#     • Не трогает уведомления другого юзера
# ──────────────────────────────────────────────────────────────────────────────

from django.contrib.auth import get_user_model
from django.test import TestCase

from crm.notification.models import Notification, NotificationKind
from crm.notification.services import inapp_service

User = get_user_model()


def _make_user(username):
    return User.objects.create_user(username=username, password="x")


class CreateInappTests(TestCase):

    def setUp(self):
        self.recipient = _make_user("recipient_ia")
        self.actor = _make_user("actor_ia")

    def test_no_recipients_returns_empty_list(self):
        # Пустой список получателей → функция возвращает [] и не пишет в БД.
        result = inapp_service.create_inapp(
            kind=NotificationKind.SYSTEM,
            template_name="t.txt",
            payload={},
            recipients=[],
        )
        self.assertEqual(result, [])
        self.assertEqual(Notification.objects.count(), 0)

    def test_single_recipient_creates_one_notification(self):
        result = inapp_service.create_inapp(
            kind=NotificationKind.SYSTEM,
            template_name="t.txt",
            payload={"key": "value"},
            recipients=[self.recipient],
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(Notification.objects.count(), 1)

    def test_multiple_recipients_creates_one_per_recipient(self):
        r2 = _make_user("recipient_ia2")
        result = inapp_service.create_inapp(
            kind=NotificationKind.ASSIGNMENT,
            template_name="t.txt",
            payload={},
            recipients=[self.recipient, r2],
        )
        self.assertEqual(len(result), 2)
        self.assertEqual(Notification.objects.count(), 2)

    def test_created_notification_has_correct_recipient(self):
        inapp_service.create_inapp(
            kind=NotificationKind.STATUS_CHANGE,
            template_name="status.txt",
            payload={},
            recipients=[self.recipient],
        )
        notif = Notification.objects.get(recipient=self.recipient)
        self.assertEqual(notif.recipient, self.recipient)

    def test_created_notification_has_correct_kind(self):
        inapp_service.create_inapp(
            kind=NotificationKind.REVIEW_REQUEST,
            template_name="t.txt",
            payload={},
            recipients=[self.recipient],
        )
        notif = Notification.objects.first()
        self.assertEqual(notif.kind, NotificationKind.REVIEW_REQUEST)

    def test_unknown_kind_defaults_to_system(self):
        # Если kind не из NotificationKind.values → логируется warning и ставится SYSTEM.
        inapp_service.create_inapp(
            kind="TOTALLY_UNKNOWN",
            template_name="t.txt",
            payload={},
            recipients=[self.recipient],
        )
        notif = Notification.objects.first()
        self.assertEqual(notif.kind, NotificationKind.SYSTEM)

    def test_with_actor_fills_actor_field(self):
        inapp_service.create_inapp(
            kind=NotificationKind.ASSIGNMENT,
            template_name="t.txt",
            payload={},
            recipients=[self.recipient],
            actor=self.actor,
        )
        notif = Notification.objects.first()
        self.assertEqual(notif.actor, self.actor)

    def test_without_actor_leaves_actor_null(self):
        inapp_service.create_inapp(
            kind=NotificationKind.SYSTEM,
            template_name="t.txt",
            payload={},
            recipients=[self.recipient],
        )
        notif = Notification.objects.first()
        self.assertIsNone(notif.actor)

    def test_payload_stored_in_db(self):
        inapp_service.create_inapp(
            kind=NotificationKind.SYSTEM,
            template_name="t.txt",
            payload={"request_id": 42},
            recipients=[self.recipient],
        )
        notif = Notification.objects.first()
        self.assertEqual(notif.payload["request_id"], 42)

    def test_new_notification_is_unread(self):
        # Все только что созданные уведомления должны быть непрочитанными.
        inapp_service.create_inapp(
            kind=NotificationKind.SYSTEM,
            template_name="t.txt",
            payload={},
            recipients=[self.recipient],
        )
        notif = Notification.objects.first()
        self.assertFalse(notif.is_read)


# ─────────────────────────── mark_read ────────────────────────────────────────


class MarkReadTests(TestCase):

    def setUp(self):
        self.user = _make_user("reader")
        self.other = _make_user("other_reader")
        self.notif = Notification.objects.create(
            recipient=self.user,
            kind=NotificationKind.SYSTEM,
            template_name="t.txt",
        )

    def test_marks_unread_notification_as_read(self):
        result = inapp_service.mark_read(self.notif, by_user=self.user)
        self.assertTrue(result)
        self.notif.refresh_from_db()
        self.assertTrue(self.notif.is_read)

    def test_stamps_read_at_timestamp(self):
        # После пометки read_at должен быть заполнен.
        inapp_service.mark_read(self.notif, by_user=self.user)
        self.notif.refresh_from_db()
        self.assertIsNotNone(self.notif.read_at)

    def test_idempotent_already_read_returns_false(self):
        # Повторный вызов на уже прочитанном → False (не переписывает read_at).
        inapp_service.mark_read(self.notif, by_user=self.user)
        first_read_at = Notification.objects.get(pk=self.notif.pk).read_at

        result = inapp_service.mark_read(self.notif, by_user=self.user)
        self.assertFalse(result)

        # read_at не должен измениться при повторном вызове.
        self.notif.refresh_from_db()
        self.assertEqual(self.notif.read_at, first_read_at)

    def test_wrong_user_returns_false_and_does_not_mark(self):
        # Чужой пользователь не может прочитать чужое уведомление.
        result = inapp_service.mark_read(self.notif, by_user=self.other)
        self.assertFalse(result)
        self.notif.refresh_from_db()
        self.assertFalse(self.notif.is_read)


# ─────────────────────────── mark_all_read ────────────────────────────────────


class MarkAllReadTests(TestCase):

    def setUp(self):
        self.user = _make_user("bulk_reader")
        self.other = _make_user("other_bulk")

    def _create_notif(self, user, is_read=False):
        return Notification.objects.create(
            recipient=user,
            kind=NotificationKind.SYSTEM,
            template_name="t.txt",
            is_read=is_read,
        )

    def test_marks_all_unread_of_user(self):
        self._create_notif(self.user)
        self._create_notif(self.user)
        count = inapp_service.mark_all_read(self.user)
        self.assertEqual(count, 2)
        self.assertEqual(
            Notification.objects.filter(recipient=self.user, is_read=False).count(), 0
        )

    def test_already_read_not_counted(self):
        self._create_notif(self.user, is_read=True)
        self._create_notif(self.user, is_read=False)
        count = inapp_service.mark_all_read(self.user)
        # Только 1 непрочитанное → обновляется 1.
        self.assertEqual(count, 1)

    def test_does_not_touch_other_users_notifications(self):
        self._create_notif(self.other)  # другой пользователь
        inapp_service.mark_all_read(self.user)
        # Уведомление другого пользователя должно остаться непрочитанным.
        self.assertEqual(
            Notification.objects.filter(recipient=self.other, is_read=False).count(), 1
        )

    def test_returns_zero_when_no_unread(self):
        count = inapp_service.mark_all_read(self.user)
        self.assertEqual(count, 0)
