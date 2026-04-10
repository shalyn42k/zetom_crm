# test made by codex



from django.test import TestCase
from unittest.mock import patch
 


from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from zetom.emails.email_utils import send_notification_to_staff
from zetom.forms import AddRequestFormNull
from zetom.models import Request_Null


class AddRequestFormNullTests(TestCase):
    def test_form_is_valid_with_correct_polish_data(self):
        form = AddRequestFormNull(
            data={
                "phone": "+48501600300",
                "company_name": "Zetom Sp. z o.o.",
                "email": "contact@zetom.pl",
                "company_nip": "7322215365",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_form_is_invalid_with_bad_nip(self):
        form = AddRequestFormNull(
            data={
                "phone": "+48501600300",
                "company_name": "Zetom Sp. z o.o.",
                "email": "contact@zetom.pl",
                "company_nip": "not-a-nip",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("company_nip", form.errors)


class EmailNotificationTests(TestCase):
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_send_notification_to_staff_creates_email_message(self):
        request_obj = Request_Null.objects.create(
            phone="+48501600300",
            company_name="Zetom Sp. z o.o.",
            email="contact@zetom.pl",
            company_nip="7322215365",
        )

        send_notification_to_staff(request_obj)

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertIn("New notification from Zetom CRM", message.subject)
        self.assertIn(str(request_obj.id), message.subject)
        self.assertIn("Check new request", message.body)
        self.assertEqual(message.to, ["tymirapps@gmail.com"])


class EmailTemplateViewTests(TestCase):
    def test_get_returns_form_page(self):
        response = self.client.get(reverse("zetom:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Отправка данных")
        self.assertIn("form", response.context)

    @patch("zetom.views.send_notification_to_staff")
    def test_post_valid_data_saves_request_and_sends_notification(self, send_mock):
        response = self.client.post(
            reverse("zetom:index"),
            data={
                "phone": "+48501600300",
                "company_name": "Zetom Sp. z o.o.",
                "email": "contact@zetom.pl",
                "company_nip": "7322215365",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Request_Null.objects.count(), 1)
        send_mock.assert_called_once()
        self.assertContains(response, "Все заебок со всем")

    @patch("zetom.views.send_notification_to_staff", side_effect=Exception("SMTP failed"))
    def test_post_valid_data_handles_email_errors(self, _send_mock):
        response = self.client.post(
            reverse("zetom:index"),
            data={
                "phone": "+48501600300",
                "company_name": "Zetom Sp. z o.o.",
                "email": "contact@zetom.pl",
                "company_nip": "7322215365",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Request_Null.objects.count(), 1)
        self.assertContains(response, "Все ок в базе, но с почтой нет")

    def test_post_invalid_data_returns_errors(self):
        response = self.client.post(
            reverse("zetom:index"),
            data={
                "phone": "abc",
                "company_name": "",
                "email": "not-an-email",
                "company_nip": "123",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Все плохо", response.content.decode("utf-8"))
        self.assertEqual(Request_Null.objects.count(), 0)
