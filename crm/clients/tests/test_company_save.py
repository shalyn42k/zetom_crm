# claude — CompanyAdmin.change_view renders a custom template and never builds
# a ModelForm, so views.company_save is the only write path for a Company's own
# fields (before it existed, both "Edytuj" buttons on the card were dead).
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from crm.clients.models import Company


class CompanySaveTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("staff", "s@s.pl", "pass12345")
        self.client.force_login(self.user)
        self.company = Company.objects.create(
            name="Zetom Sp.", nip="1234563218", city="Warszawa",
        )
        self.url = reverse("admin:clients_company_save", args=[self.company.pk])

    def _post(self, **data):
        return self.client.post(self.url, data, HTTP_HOST="127.0.0.1")

    def test_saves_podstawowe(self):
        resp = self._post(
            section="podstawowe", name="Zetom S.A.", nip="123-456-32-18",
            regon="123456785", type_supplier="lokalny",
        )
        self.assertTrue(resp.json()["ok"])
        self.company.refresh_from_db()
        self.assertEqual(self.company.name, "Zetom S.A.")
        self.assertEqual(self.company.nip, "1234563218")  # normalized
        self.assertEqual(self.company.type_supplier, "lokalny")
        # the other section is untouched by a partial POST
        self.assertEqual(self.company.city, "Warszawa")

    def test_saves_szczegolowe(self):
        resp = self._post(
            section="szczegolowe", country="Polska", city="Kraków",
            voivodeship="małopolskie", post_code="30-001", street="Przemysłowa 12",
            email="biuro@zetom.pl", phone="+48501600300",
        )
        self.assertTrue(resp.json()["ok"])
        self.company.refresh_from_db()
        self.assertEqual(self.company.city, "Kraków")
        self.assertEqual(self.company.email, "biuro@zetom.pl")
        # the other section is untouched
        self.assertEqual(self.company.name, "Zetom Sp.")

    def test_rejects_empty_name(self):
        resp = self._post(section="podstawowe", name="  ", nip="", regon="", type_supplier="")
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["ok"])
        self.company.refresh_from_db()
        self.assertEqual(self.company.name, "Zetom Sp.")

    def test_rejects_bad_nip_checksum(self):
        resp = self._post(
            section="podstawowe", name="Zetom Sp.", nip="1234563219",
            regon="", type_supplier="",
        )
        self.assertEqual(resp.status_code, 400)
        self.company.refresh_from_db()
        self.assertEqual(self.company.nip, "1234563218")

    # claude — uniq_company_nip would otherwise surface as a 500 IntegrityError.
    def test_rejects_duplicate_nip(self):
        Company.objects.create(name="Inna", nip="5262706346")
        resp = self._post(
            section="podstawowe", name="Zetom Sp.", nip="5262706346",
            regon="", type_supplier="",
        )
        self.assertEqual(resp.status_code, 400)
        self.company.refresh_from_db()
        self.assertEqual(self.company.nip, "1234563218")

    def test_clears_nip(self):
        resp = self._post(section="podstawowe", name="Zetom Sp.", nip="", regon="", type_supplier="")
        self.assertTrue(resp.json()["ok"])
        self.company.refresh_from_db()
        self.assertIsNone(self.company.nip)

    def test_rejects_unknown_supplier_type(self):
        resp = self._post(
            section="podstawowe", name="Zetom Sp.", nip="", regon="", type_supplier="kosmiczny",
        )
        self.assertEqual(resp.status_code, 400)

    def test_rejects_bad_email_and_phone(self):
        for field, value in (("email", "not-an-email"), ("phone", "not-a-phone")):
            with self.subTest(field=field):
                payload = {
                    "section": "szczegolowe", "country": "", "city": "", "voivodeship": "",
                    "post_code": "", "street": "", "email": "", "phone": "",
                }
                payload[field] = value
                resp = self.client.post(self.url, payload, HTTP_HOST="127.0.0.1")
                self.assertEqual(resp.status_code, 400)

    def test_rejects_unknown_section(self):
        resp = self._post(section="wymyslona", name="X")
        self.assertEqual(resp.status_code, 400)

    def test_get_not_allowed(self):
        resp = self.client.get(self.url, HTTP_HOST="127.0.0.1")
        self.assertEqual(resp.status_code, 405)
