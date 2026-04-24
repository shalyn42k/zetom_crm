from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from crm.notification.services.notification_service import \
    send_notification_to_staff
from crm.zetom.models import RequestNull

VALID_POST = {
    "phone": "+48501600300",
    "company_name": "Zetom Sp. z o.o.",
    "email": "contact@zetom.pl",
    "company_nip": "7322215365",
}


class EmailTemplateViewTests(TestCase):
    url = reverse("zetom:index")

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_superuser(
            username="admin", email="a@a.com", password="x"
        )

    def setUp(self):
        # template extends Unfold admin base; needs an authenticated session
        self.client.force_login(self.user)

    def test_get_returns_form_page(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Submit your request")
        self.assertIn("form", response.context)

    @patch("crm.zetom.views.send_notification_to_staff")
    def test_post_valid_saves_sends_notification_and_redirects(self, send_mock):
        response = self.client.post(self.url, data=VALID_POST)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(RequestNull.objects.count(), 1)
        new_obj = RequestNull.objects.first()
        send_mock.assert_called_once_with(new_obj)
        self.assertEqual(
            response["Location"],
            reverse("admin:zetom_requestnull_change", args=[new_obj.pk]),
        )

    @patch(
        "crm.zetom.views.send_notification_to_staff",
        side_effect=Exception("SMTP down"),
    )
    def test_post_valid_handles_notification_failure(self, _):
        response = self.client.post(self.url, data=VALID_POST)

        # record is still saved even if notification fails; template re-rendered
        self.assertEqual(response.status_code, 200)
        self.assertEqual(RequestNull.objects.count(), 1)

    def test_post_invalid_returns_errors_and_does_not_save(self):
        response = self.client.post(
            self.url,
            data={
                "phone": "abc",
                "company_name": "",
                "email": "not-email",
                "company_nip": "123",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(RequestNull.objects.count(), 0)
        form = response.context["form"]
        self.assertFalse(form.is_valid())
        self.assertIn("phone", form.errors)
        self.assertIn("email", form.errors)
        self.assertIn("company_nip", form.errors)


class NotificationServiceIntegrationTests(TestCase):
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_send_notification_to_staff_creates_email(self):
        obj = RequestNull.objects.create(**VALID_POST)
        send_notification_to_staff(obj)
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertIn(str(obj.id), msg.subject)
        self.assertIn(obj.company_name, msg.subject)
