# claude — Add Client modal backend (design_handoff_add_client). One POST,
# two branches: `kind=firma` writes a Company, `kind=osoba` writes a Client.
# Field guards are the same helpers the edit modals use, so a value rejected
# there is rejected here too.
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from crm.clients.models import Client, Company
from crm.status_manager.services.statuses import RequestStatus
from crm.zetom.models import Oferta, RequestClientLink, RequestMain

BASE_REQ = {
    "first_name": "Jan",
    "last_name": "Kowalski",
    "phone": "+48501600300",
    "email": "jan@zetom.pl",
    "company_name": "Zetom",
}

OSOBA = {"kind": "osoba", "first_name": "Anna", "last_name": "Nowak"}
FIRMA = {
    "kind": "firma", "name": "Zetom Sp.", "nip": "", "regon": "", "type_supplier": "",
    "country": "", "city": "", "voivodeship": "", "post_code": "", "street": "",
    "phone": "", "email": "",
}


class ClientCreateTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("staff", "s@s.pl", "pass12345")
        self.client.force_login(self.user)
        self.url = reverse("admin:clients_client_create")

    def _post(self, payload):
        return self.client.post(self.url, payload, HTTP_HOST="127.0.0.1")

    def test_creates_person(self):
        resp = self._post({**OSOBA, "phone": "+48501600300", "email": "a@n.pl"})
        body = resp.json()
        self.assertTrue(body["ok"])
        person = Client.objects.get(first_name="Anna", last_name="Nowak")
        self.assertEqual(body["url"], reverse("admin:clients_client_change", args=[person.pk]))
        self.assertEqual(person.email, "a@n.pl")

    def test_creates_company(self):
        resp = self._post({**FIRMA, "nip": "123-456-32-18", "city": "Kraków"})
        body = resp.json()
        self.assertTrue(body["ok"])
        company = Company.objects.get(name="Zetom Sp.")
        self.assertEqual(body["url"], reverse("admin:clients_company_change", args=[company.pk]))
        self.assertEqual(company.nip, "1234563218")  # normalized
        self.assertEqual(company.city, "Kraków")

    def test_rejects_unknown_kind(self):
        resp = self._post({"kind": "kosmita", "first_name": "X"})
        self.assertEqual(resp.status_code, 400)

    def test_person_needs_a_name(self):
        resp = self._post({"kind": "osoba", "first_name": "", "last_name": ""})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(Client.objects.exists())

    def test_company_needs_a_name(self):
        resp = self._post({**FIRMA, "name": "  "})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(Company.objects.exists())

    # claude — same guards as the edit modals, verified through the create path.
    def test_rejects_bad_field_values(self):
        cases = [
            ({**OSOBA, "phone": "not-a-phone"}, "person phone"),
            ({**OSOBA, "email": "nope"}, "person email"),
            ({**FIRMA, "nip": "1234563219"}, "company nip checksum"),
            ({**FIRMA, "phone": "12345"}, "company phone"),
            ({**FIRMA, "type_supplier": "kosmiczny"}, "supplier type"),
        ]
        for payload, label in cases:
            with self.subTest(case=label):
                resp = self._post(payload)
                self.assertEqual(resp.status_code, 400)
        self.assertFalse(Client.objects.exists())
        self.assertFalse(Company.objects.exists())

    def test_rejects_duplicate_nip(self):
        Company.objects.create(name="Inna", nip="1234563218")
        resp = self._post({**FIRMA, "nip": "1234563218"})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Company.objects.count(), 1)

    def test_requires_edit_permission(self):
        self.client.logout()
        self.client.force_login(_view_only_user())
        resp = self._post(OSOBA)
        self.assertEqual(resp.status_code, 403)

    def test_list_renders_the_modal(self):
        resp = self.client.get(
            reverse("admin:clients_client_changelist"), HTTP_HOST="127.0.0.1",
        )
        self.assertContains(resp, "addClientModal()")
        self.assertContains(resp, "type-opt")
        self.assertContains(resp, "link-panel")

    # claude — no add permission, no modal and no button; the endpoint refuses
    # the same user anyway (test_requires_edit_permission above).
    def test_read_only_user_gets_no_modal(self):
        self.client.logout()
        self.client.force_login(_view_only_user())
        resp = self.client.get(
            reverse("admin:clients_client_changelist"), HTTP_HOST="127.0.0.1",
        )
        self.assertNotContains(resp, "type-opt")
        # the button, not the factory — addClientModal() itself is defined
        # unconditionally because x-data on .cc-stage evaluates for everyone
        self.assertNotContains(resp, '@click="openModal()"')


# claude — staff user carrying view_clients only (the RBAC signal's default
# role would otherwise hand out edit_clients too).
def _view_only_user():
    from crm.users.models import Permission

    user = User.objects.create_user("viewer", "v@v.pl", "pass12345", is_staff=True)
    profile = user.profile
    profile.otp_exempt = True
    profile.role = None
    profile.save()
    profile.extra_permissions.add(Permission.objects.get(code="view_clients"))
    return user


class ClientCreateLinkTest(TestCase):
    """The optional 'Powiąż zgłoszenie' step."""

    def setUp(self):
        self.user = User.objects.create_superuser("staff", "s@s.pl", "pass12345")
        self.client.force_login(self.user)
        self.url = reverse("admin:clients_client_create")
        self.zgloszenie = RequestMain.objects.create(**BASE_REQ)
        self.oferta = Oferta.objects.create(**BASE_REQ)

    def _post(self, payload):
        return self.client.post(self.url, payload, HTTP_HOST="127.0.0.1")

    def test_person_links_through_m2m(self):
        resp = self._post({**OSOBA, "req_type": "main", "req_pk": self.zgloszenie.pk})
        self.assertTrue(resp.json()["ok"])
        person = Client.objects.get(first_name="Anna")
        self.assertTrue(
            RequestClientLink.objects.filter(request=self.zgloszenie, client=person).exists()
        )

    def test_person_can_link_a_child_document(self):
        resp = self._post({**OSOBA, "req_type": "oferta", "req_pk": self.oferta.pk})
        self.assertTrue(resp.json()["ok"])
        person = Client.objects.get(first_name="Anna")
        self.assertIn(person, self.oferta.clients.all())

    def test_company_links_through_fk(self):
        resp = self._post({**FIRMA, "req_type": "main", "req_pk": self.zgloszenie.pk})
        self.assertTrue(resp.json()["ok"])
        self.zgloszenie.refresh_from_db()
        self.assertEqual(self.zgloszenie.company, Company.objects.get(name="Zetom Sp."))

    # claude — only RequestMain has the Company FK, so a child document can
    # never carry a firm. Refused server-side, not merely hidden in the picker.
    def test_company_cannot_link_a_child_document(self):
        resp = self._post({**FIRMA, "req_type": "oferta", "req_pk": self.oferta.pk})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(Company.objects.exists())

    # claude — repointing would silently rewrite an existing relationship.
    def test_company_refuses_a_request_owned_by_another_firm(self):
        other = Company.objects.create(name="Inna")
        self.zgloszenie.company = other
        self.zgloszenie.save(update_fields=["company"])
        resp = self._post({**FIRMA, "req_type": "main", "req_pk": self.zgloszenie.pk})
        self.assertEqual(resp.status_code, 400)
        self.zgloszenie.refresh_from_db()
        self.assertEqual(self.zgloszenie.company, other)
        # the whole POST rolls back — no half-created firm left behind
        self.assertFalse(Company.objects.filter(name="Zetom Sp.").exists())

    def test_dead_request_cannot_be_linked(self):
        self.zgloszenie.status = RequestStatus.deleted
        self.zgloszenie.save(update_fields=["status"])
        resp = self._post({**OSOBA, "req_type": "main", "req_pk": self.zgloszenie.pk})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(Client.objects.exists())

    def test_no_pick_creates_without_a_link(self):
        resp = self._post({**OSOBA, "req_type": "", "req_pk": ""})
        self.assertTrue(resp.json()["ok"])
        self.assertFalse(RequestClientLink.objects.exists())
