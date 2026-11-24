# claude
# ──────────────────────────────────────────────────────────────────────────────
# ТЕСТЫ duplicate-ops в Validation Window (_dispatch_dupe_op)
#
#   delete_duplicate        — soft-delete текущего RequestNull (→ trash)
#   delete_existing:null    — soft-delete существующего RequestNull (→ trash)
#   delete_existing:main    — soft-cancel существующего RequestMain
#   delete_all_dupes        — soft-delete/cancel всех дубликатов разом
#   update_existing:*       — перенос данных текущего → существующий, soft-delete текущего
#   update_current:*        — перенос существующего → текущий, остаться
# ──────────────────────────────────────────────────────────────────────────────

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from crm.status_manager.services.statuses import RequestStatus
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
class VwDupeOpsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_superuser("admin", "a@a.com", "x")

    def setUp(self):
        self.client.force_login(self.user)
        self.rn = RequestNull.objects.create(**BASE)

    def _url(self):
        return reverse("admin:zetom_requestnull_validate", args=[self.rn.pk])

    def test_delete_current_soft_deletes(self, _p):
        self.client.post(self._url(), {"__action": "delete_duplicate"})
        # gone from the live manager, still recoverable from trash
        self.assertFalse(RequestNull.objects.filter(pk=self.rn.pk).exists())
        self.assertTrue(
            RequestNull.objects.all_with_deleted().filter(pk=self.rn.pk).exists()
        )

    def test_delete_existing_null_soft_deletes(self, _p):
        other = RequestNull.objects.create(**BASE)
        self.client.post(self._url(), {"__action": f"delete_existing:null:{other.pk}"})
        self.assertFalse(RequestNull.objects.filter(pk=other.pk).exists())
        self.assertTrue(
            RequestNull.objects.all_with_deleted().filter(pk=other.pk).exists()
        )
        # current survives
        self.assertTrue(RequestNull.objects.filter(pk=self.rn.pk).exists())

    def test_delete_existing_main_soft_cancels(self, _p):
        main = RequestMain.objects.create(**BASE)
        self.client.post(self._url(), {"__action": f"delete_existing:main:{main.pk}"})
        main.refresh_from_db()
        self.assertEqual(main.status, RequestStatus.cancelled)

    def test_delete_all_dupes_soft_removes_every_match(self, _p):
        null_dupe = RequestNull.objects.create(**BASE)
        main_dupe = RequestMain.objects.create(**BASE)
        self.client.post(self._url(), {"__action": "delete_all_dupes"})
        # sibling RequestNull soft-deleted
        self.assertFalse(RequestNull.objects.filter(pk=null_dupe.pk).exists())
        self.assertTrue(
            RequestNull.objects.all_with_deleted().filter(pk=null_dupe.pk).exists()
        )
        # RequestMain soft-cancelled
        main_dupe.refresh_from_db()
        self.assertEqual(main_dupe.status, RequestStatus.cancelled)
        # current lead untouched
        self.assertTrue(RequestNull.objects.filter(pk=self.rn.pk).exists())

    def test_update_existing_merges_and_removes_current(self, _p):
        main = RequestMain.objects.create(**BASE)
        self.rn.company_name = "NewName"
        self.rn.save()
        self.client.post(self._url(), {"__action": f"update_existing:main:{main.pk}"})
        main.refresh_from_db()
        self.assertEqual(main.company_name, "NewName")
        # current RequestNull removed (soft → trash)
        self.assertFalse(RequestNull.objects.filter(pk=self.rn.pk).exists())
        self.assertTrue(
            RequestNull.objects.all_with_deleted().filter(pk=self.rn.pk).exists()
        )

    def test_update_current_pulls_and_keeps(self, _p):
        main = RequestMain.objects.create(**BASE)
        main.company_name = "Canonical"
        main.save()
        self.client.post(self._url(), {"__action": f"update_current:main:{main.pk}"})
        self.rn.refresh_from_db()
        self.assertEqual(self.rn.company_name, "Canonical")
        # current still exists, main untouched
        self.assertTrue(RequestNull.objects.filter(pk=self.rn.pk).exists())

    def test_bad_target_redirects_without_crash(self, _p):
        resp = self.client.post(self._url(), {"__action": "delete_existing:main:999999"})
        self.assertEqual(resp.status_code, 302)
