# ──────────────────────────────────────────────────────────────────────────────
# ТЕСТЫ mail_service.py
#
# Что тестируем:
#   _send() / send_to_client() / send_to_staff():
#     • Нет получателей → ничего не создаётся в БД, возвращает []
#     • Успешная отправка → EmailNotification со статусом SENT, sent_at заполнен
#     • SMTP-ошибка → EmailNotification со статусом FAILED, status_reason заполнен
#       (исключение гасится — вызывающий код не падает)
#     • Несколько получателей → по одной записи на каждого
#
# Как реально работает отправка (прочитав mail_service.py):
#   Используется get_connection() + EmailMessage.send() — НЕ send_mail.
#   Это значит patch нужен на 'django.core.mail.EmailMessage.send',
#   а не на несуществующий mail_service.send_mail.
#
# @override_settings(EMAIL_BACKEND=locmem):
#   locmem backend перехватывает EmailMessage.send() и складывает письма
#   в django.core.mail.outbox — стандартный Django-способ тестировать email.
# ──────────────────────────────────────────────────────────────────────────────

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings

from crm.notification.models import EmailNotification, EmailStatus
from crm.notification.services import mail_service

User = get_user_model()


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@test.com",
)
class SendMailServiceTests(TestCase):

    # ── Нет получателей ────────────────────────────────────────────────────────

    def test_no_recipients_returns_empty_list(self):
        result = mail_service._send(
            recipients=[],
            subject="Test",
            body="Body",
        )
        self.assertEqual(result, [])

    def test_no_recipients_creates_no_db_record(self):
        mail_service._send(recipients=[], subject="Test", body="Body")
        self.assertEqual(EmailNotification.objects.count(), 0)

    # ── Успешная отправка ──────────────────────────────────────────────────────

    def test_successful_send_creates_email_notification(self):
        mail_service._send(
            recipients=["client@test.com"],
            subject="Hello",
            body="World",
        )
        self.assertEqual(EmailNotification.objects.count(), 1)

    def test_successful_send_sets_status_sent(self):
        mail_service._send(
            recipients=["client@test.com"],
            subject="Hello",
            body="World",
        )
        record = EmailNotification.objects.first()
        self.assertEqual(record.status, EmailStatus.SENT)

    def test_successful_send_stamps_sent_at(self):
        mail_service._send(
            recipients=["client@test.com"],
            subject="Hello",
            body="World",
        )
        record = EmailNotification.objects.first()
        self.assertIsNotNone(record.sent_at)

    def test_successful_send_puts_email_in_outbox(self):
        # locmem backend складывает письма в mail.outbox.
        # _send() использует EmailMessage + get_connection() — оба совместимы с locmem.
        mail_service._send(
            recipients=["client@test.com"],
            subject="Check outbox",
            body="Body text",
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Check outbox")
        self.assertEqual(mail.outbox[0].to, ["client@test.com"])

    def test_multiple_recipients_creates_one_record_each(self):
        # Каждому получателю — отдельная запись EmailNotification для аудита.
        mail_service._send(
            recipients=["a@test.com", "b@test.com"],
            subject="Multi",
            body="Body",
        )
        self.assertEqual(EmailNotification.objects.count(), 2)
        self.assertEqual(len(mail.outbox), 2)

    def test_record_stores_subject_and_recipient(self):
        mail_service._send(
            recipients=["store@test.com"],
            subject="Stored subject",
            body="Body",
        )
        record = EmailNotification.objects.first()
        self.assertEqual(record.recipient_email, "store@test.com")
        self.assertEqual(record.subject, "Stored subject")

    def test_payload_stored_in_record(self):
        mail_service._send(
            recipients=["p@test.com"],
            subject="Payload",
            body="Body",
            payload={"req_id": 7},
        )
        record = EmailNotification.objects.first()
        self.assertEqual(record.payload["req_id"], 7)

    def test_actor_stored_in_record(self):
        actor = User.objects.create_user(username="mail_actor", password="x")
        mail_service._send(
            recipients=["p@test.com"],
            subject="With actor",
            body="Body",
            actor=actor,
        )
        record = EmailNotification.objects.first()
        self.assertEqual(record.actor, actor)

    # ── SMTP-ошибка — исключение гасится ──────────────────────────────────────
    # Мокируем EmailMessage.send() — именно этот метод вызывает mail_service._send().
    # send_mail в файле не импортируется; используется get_connection() + EmailMessage.

    @patch("django.core.mail.EmailMessage.send", side_effect=Exception("SMTP Connection refused"))
    def test_smtp_failure_sets_status_failed(self, _mock):
        mail_service._send(
            recipients=["fail@test.com"],
            subject="Will fail",
            body="Body",
        )
        record = EmailNotification.objects.first()
        self.assertEqual(record.status, EmailStatus.FAILED)

    @patch("django.core.mail.EmailMessage.send", side_effect=Exception("SMTP Connection refused"))
    def test_smtp_failure_stores_reason(self, _mock):
        mail_service._send(
            recipients=["fail@test.com"],
            subject="Will fail",
            body="Body",
        )
        record = EmailNotification.objects.first()
        self.assertIn("SMTP Connection refused", record.status_reason)

    @patch("django.core.mail.EmailMessage.send", side_effect=Exception("SMTP Connection refused"))
    def test_smtp_failure_does_not_raise(self, _mock):
        # Критично: исключение должно быть поглощено, не бросаться наружу.
        # Иначе SMTP-падение сломает вью/сигнал, который вызвал отправку.
        try:
            mail_service._send(
                recipients=["fail@test.com"],
                subject="Will fail",
                body="Body",
            )
        except Exception:
            self.fail("_send() должен гасить исключение, а не пробрасывать его")

    # ── Публичные обёртки ──────────────────────────────────────────────────────

    def test_send_to_client_sends_to_single_address(self):
        mail_service.send_to_client(
            to="single@test.com",
            subject="Client mail",
            body="Hi client",
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["single@test.com"])

    def test_send_to_staff_sends_to_all_addresses(self):
        mail_service.send_to_staff(
            subject="Staff mail",
            body="Hi staff",
            recipients=["staff1@test.com", "staff2@test.com"],
        )
        self.assertEqual(len(mail.outbox), 2)
