# claude
"""Company data by NIP from the MF VAT register — the register is mocked."""
from unittest.mock import MagicMock, patch

import requests
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from crm.clients.services_nip_lookup import split_address

User = get_user_model()

ORLEN = {"result": {"subject": {
    "name": "ORLEN SPÓŁKA AKCYJNA", "nip": "7740001454", "regon": "610188201", "krs": "0000028860",
    "statusVat": "Czynny", "workingAddress": "CHEMIKÓW 7, 09-411 PŁOCK", "residenceAddress": None,
}}}


def _response(status=200, payload=None):
    r = MagicMock(status_code=status)
    r.json.return_value = payload
    return r


class NipLookupTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_superuser("boss", "b@zetom.pl", "x")
        self.client.force_login(self.user)
        self.url = reverse("clients:nip_lookup")

    @patch("crm.clients.services_nip_lookup.requests.get", return_value=_response(200, ORLEN))
    def test_found(self, get):
        d = self.client.get(self.url, {"nip": "774-000-14-54"}).json()
        self.assertTrue(d["ok"])
        self.assertEqual(d["name"], "Orlen Spółka Akcyjna")
        self.assertEqual((d["street"], d["post_code"], d["city"]), ("Chemików 7", "09-411", "Płock"))
        self.assertEqual(d["regon"], "610188201")
        self.client.get(self.url, {"nip": "7740001454"})
        self.assertEqual(get.call_count, 1)  # cached

    @patch("crm.clients.services_nip_lookup.requests.get")
    def test_invalid_nip_never_calls_the_register(self, get):
        d = self.client.get(self.url, {"nip": "1234567890"}).json()
        self.assertFalse(d["ok"])
        get.assert_not_called()

    @patch("crm.clients.services_nip_lookup.requests.get", return_value=_response(200, {"result": {"subject": None}}))
    def test_not_in_register(self, _get):
        d = self.client.get(self.url, {"nip": "7740001454"}).json()
        self.assertFalse(d["ok"])

    @patch("crm.clients.services_nip_lookup.requests.get", side_effect=requests.ConnectionError())
    def test_register_down(self, _get):
        d = self.client.get(self.url, {"nip": "7740001454"}).json()
        self.assertFalse(d["ok"])
        self.assertTrue(d["error"])

    def test_needs_permission(self):
        from crm.users.models import Role
        u = User.objects.create_user("nobody", "n@zetom.pl", "x", is_staff=True)
        Role.objects.get(code="specialist").permissions.filter(code="view_clients").delete()
        self.client.force_login(u)
        self.assertEqual(self.client.get(self.url, {"nip": "7740001454"}).status_code, 403)

    def test_split_address(self):
        self.assertEqual(split_address("UL. PRZEMYSŁOWA 12/3, 00-001 WARSZAWA"),
                         {"street": "UL. PRZEMYSŁOWA 12/3", "post_code": "00-001", "city": "WARSZAWA"})
        self.assertEqual(split_address("bez kodu")["street"], "bez kodu")

    def test_company_dialogs_offer_the_button(self):
        html = self.client.get(reverse("admin:clients_client_changelist")).content.decode()
        self.assertIn(self.url, html)
