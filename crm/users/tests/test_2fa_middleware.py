# claude — Enforce2FAMiddleware is switched off for the rest of the suite
# (_RUNNING_TESTS), so nothing covered it. Here it's switched back on.
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

_SIMPLE_STATIC = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(STORAGES=_SIMPLE_STATIC)
@patch("crm.users.middleware._RUNNING_TESTS", False)
class Enforce2FAEverywhereTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser("boss", "b@zetom.pl", "x")

    def setUp(self):
        # Password accepted, OTP not yet.
        self.client.force_login(self.user)

    def assertSentTo2FA(self, url):
        r = self.client.get(url)
        self.assertEqual(r.status_code, 302, url)
        self.assertTrue(r["Location"].startswith(reverse("otp_gate")), (url, r["Location"]))

    def test_admin_pages_need_2fa(self):
        self.assertSentTo2FA(f"/{settings.ADMIN_URL}")

    def test_pages_outside_admin_need_2fa_too(self):
        for url in (
            reverse("user_list"),
            reverse("user_profile_edit"),
            reverse("clients:search") + "?q=a",
            reverse("notification:inbox"),
            reverse("notification:unread_count"),
            reverse("zetom:attachment", args=[1]),
        ):
            self.assertSentTo2FA(url)

    def test_next_keeps_the_query_string(self):
        r = self.client.get(reverse("clients:search") + "?q=a&b=1")
        self.assertIn("next=%2Fclients%2Fsearch%2F%3Fq%3Da%26b%3D1", r["Location"])

    def test_2fa_page_public_form_and_logout_stay_open(self):
        self.assertEqual(self.client.get(reverse("otp_gate")).status_code, 200)
        self.assertEqual(self.client.get(reverse("zetom:index")).status_code, 200)
        r = self.client.post(reverse("admin:logout"))
        self.assertNotEqual(r.get("Location", ""), reverse("otp_gate"))

    def test_exempt_user_is_not_asked(self):
        self.user.profile.otp_exempt = True
        self.user.profile.save()
        r = self.client.get(reverse("user_list"))
        self.assertEqual(r.status_code, 200)
