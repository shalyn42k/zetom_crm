# claude
# ──────────────────────────────────────────────────────────────────────────────
# Type-aware trash restore:
#   RequestNull (Validation Window lead) soft-deleted → DeletedValidationRequest
#   trash → Restore → back into the Validation Window (undeleted) + inapp to staff.
# ──────────────────────────────────────────────────────────────────────────────
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from crm.notification.models import Notification
from crm.zetom.models import RequestNull

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
@patch("crm.zetom.admin.deletedvalidationrequest.user_has_perm", side_effect=always_true)
class TrashRestoreTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_superuser("admin", "a@a.com", "x")

    def setUp(self):
        self.client.force_login(self.user)
        self.rn = RequestNull.objects.create(**BASE)
        self.rn.delete()  # soft → trash

    def test_soft_deleted_lead_is_in_trash(self, _p):
        self.assertFalse(RequestNull.objects.filter(pk=self.rn.pk).exists())
        self.assertTrue(
            RequestNull.deleted_objects.filter(pk=self.rn.pk).exists()
        )

    def test_restore_brings_lead_back_and_redirects_to_vw(self, _p):
        url = reverse("admin:zetom_deletedvalidationrequest_restore", args=[self.rn.pk])
        resp = self.client.post(url)
        # undeleted → visible in the live manager again
        self.assertTrue(RequestNull.objects.filter(pk=self.rn.pk).exists())
        # redirected into the Validation Window
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            resp.url, reverse("admin:zetom_requestnull_validate", args=[self.rn.pk])
        )

    def test_restore_notifies_staff(self, _p):
        url = reverse("admin:zetom_deletedvalidationrequest_restore", args=[self.rn.pk])
        self.client.post(url)
        # admin (superuser) is the fallback recipient of the restore inapp
        self.assertTrue(
            Notification.objects.filter(recipient=self.user).exists()
        )
