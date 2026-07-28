# claude
# ──────────────────────────────────────────────────────────────────────────────
# ТЕСТЫ client-link actions на RequestMainAdmin
#
#   • link_client_action    — привязка существующего Client (M2M, идемпотентно)
#   • create_client_action  — создать Client из данных заявки + привязать
#   • unlink_client_action  — снять связь
#   • check_dupes context   — предупреждение после ручного создания
# ──────────────────────────────────────────────────────────────────────────────

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from crm.clients.models import Client
from crm.zetom.models import RequestClientLink, RequestMain

BASE_DATA = {
    "first_name": "Jan",
    "last_name": "Kowalski",
    "phone": "+48501600300",
    "email": "jan@zetom.pl",
    "company_name": "Zetom",
}

_SIMPLE_STATIC = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def always_true(*args, **kwargs):
    return True


@override_settings(STORAGES=_SIMPLE_STATIC)
@patch("crm.zetom.admin.requestmain.user_has_perm", side_effect=always_true)
class ClientLinkActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_superuser(
            username="admin", email="a@a.com", password="x"
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.req = RequestMain.objects.create(**BASE_DATA)
        # claude — Client is person-only since phase 2c (no company_name);
        # duplicate match below keys on phone+email, not company data.
        self.cl = Client.objects.create(
            first_name="Jan", last_name="Kowalski",
            phone="+48501600300", email="jan@zetom.pl",
        )

    def test_link_existing_client(self, _perm):
        url = reverse("admin:zetom_requestmain_link_client", args=[self.req.pk])
        self.client.post(url, {"client_id": self.cl.pk})
        self.assertTrue(
            RequestClientLink.objects.filter(request=self.req, client=self.cl).exists()
        )

    def test_link_is_idempotent(self, _perm):
        url = reverse("admin:zetom_requestmain_link_client", args=[self.req.pk])
        self.client.post(url, {"client_id": self.cl.pk})
        self.client.post(url, {"client_id": self.cl.pk})
        self.assertEqual(
            RequestClientLink.objects.filter(request=self.req, client=self.cl).count(), 1
        )

    def test_create_client_from_request(self, _perm):
        before = Client.objects.count()
        url = reverse("admin:zetom_requestmain_create_client", args=[self.req.pk])
        self.client.post(url)
        self.assertEqual(Client.objects.count(), before + 1)
        new_client = Client.objects.latest("created_at")
        self.assertEqual(new_client.email, "jan@zetom.pl")
        self.assertTrue(
            RequestClientLink.objects.filter(request=self.req, client=new_client).exists()
        )

    def test_unlink_client(self, _perm):
        RequestClientLink.objects.create(request=self.req, client=self.cl)
        url = reverse(
            "admin:zetom_requestmain_unlink_client", args=[self.req.pk, self.cl.pk]
        )
        self.client.post(url)
        self.assertFalse(
            RequestClientLink.objects.filter(request=self.req, client=self.cl).exists()
        )

    def test_get_request_is_noop_redirect(self, _perm):
        url = reverse("admin:zetom_requestmain_link_client", args=[self.req.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(RequestClientLink.objects.filter(request=self.req).exists())

    def test_check_duplicates_endpoint_returns_matches(self, _perm):
        # client self.cl matches phone+email exactly
        url = reverse("admin:zetom_requestmain_check_duplicates")
        resp = self.client.get(url, {"phone": "+48501600300", "email": "jan@zetom.pl"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreaterEqual(data["count"], 1)
        types = {it["type"] for it in data["items"]}
        self.assertIn("client", types)

    def test_check_duplicates_empty_when_no_signal(self, _perm):
        url = reverse("admin:zetom_requestmain_check_duplicates")
        resp = self.client.get(url, {"phone": "+48000000000", "email": "nobody@nowhere.io"})
        self.assertEqual(resp.json()["count"], 0)
