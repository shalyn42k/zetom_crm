# claude — regression: both cards used to be wired as change_form_template,
# which Django also renders from add_view. With no object in context their
# {% url ... pk %} tags raised NoReverseMatch, so "Dodaj klienta" (and the
# Company add page) answered 500 and nothing could be created from the UI.
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from crm.clients.models import Client, Company


class AddPageTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("staff", "s@s.pl", "pass12345")
        self.client.force_login(self.user)

    def test_client_add_page_renders(self):
        resp = self.client.get(reverse("admin:clients_client_add"), HTTP_HOST="127.0.0.1")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "<form")

    def test_company_add_page_renders(self):
        resp = self.client.get(reverse("admin:clients_company_add"), HTTP_HOST="127.0.0.1")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "<form")

    def test_client_can_be_created_from_add_page(self):
        resp = self.client.post(
            reverse("admin:clients_client_add"),
            {
                "first_name": "Jan", "last_name": "Nowak",
                "email": "jan@zetom.pl", "phone": "+48501600300",
                "address": "", "notes": "",
                "interactions-TOTAL_FORMS": "0", "interactions-INITIAL_FORMS": "0",
                "interactions-MIN_NUM_FORMS": "0", "interactions-MAX_NUM_FORMS": "1000",
            },
            HTTP_HOST="127.0.0.1",
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Client.objects.filter(first_name="Jan", last_name="Nowak").exists())

    # claude — the stock add form runs full_clean, so validate_nip's checksum
    # actually fires here (the card endpoints bypass forms entirely, which is
    # why company_save re-checks it by hand).
    def test_company_add_rejects_bad_nip_checksum(self):
        resp = self.client.post(
            reverse("admin:clients_company_add"),
            {
                "name": "Bad NIP", "nip": "1234563219",
                "short_name": "", "full_name": "", "regon": "", "type_supplier": "",
                "country": "", "city": "", "voivodeship": "", "post_code": "",
                "street": "", "phone": "", "email": "", "comments": "",
                "person_links-TOTAL_FORMS": "0", "person_links-INITIAL_FORMS": "0",
                "person_links-MIN_NUM_FORMS": "0", "person_links-MAX_NUM_FORMS": "1000",
            },
            HTTP_HOST="127.0.0.1",
        )
        self.assertEqual(resp.status_code, 200)  # re-rendered with errors
        self.assertFalse(Company.objects.filter(name="Bad NIP").exists())
