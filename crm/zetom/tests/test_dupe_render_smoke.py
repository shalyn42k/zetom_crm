# claude
# Smoke: страницы с новыми панелями дубликатов должны рендериться (200),
# без TemplateSyntaxError / NoReverseMatch.

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from crm.zetom.models import RequestMain, RequestNull

BASE = {
    "first_name": "Jan", "last_name": "Kowalski",
    "phone": "+48501600300", "email": "jan@zetom.pl", "company_name": "Zetom",
}

_SIMPLE_STATIC = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def always_true(*args, **kwargs):
    return True


@override_settings(STORAGES=_SIMPLE_STATIC)
@patch("crm.zetom.admin.base.user_has_perm", side_effect=always_true)
class DupeRenderSmokeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_superuser("admin", "a@a.com", "x")

    def setUp(self):
        self.client.force_login(self.user)

    def test_validation_window_renders_with_dupe_panel(self, _perm):
        rn = RequestNull.objects.create(**BASE)
        RequestMain.objects.create(**BASE)  # strong dupe
        url = reverse("admin:zetom_requestnull_validate", args=[rn.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "RequestMain")

    def test_requestmain_change_renders_with_linker(self, _perm):
        req = RequestMain.objects.create(**BASE)
        url = reverse("admin:zetom_requestmain_change", args=[req.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Linked clients")

    def test_requestmain_add_renders_dupe_popup_shell(self, _perm):
        url = reverse("admin:zetom_requestmain_add")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "rm-dupe-check")
