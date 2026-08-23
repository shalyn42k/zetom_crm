# claude — ClientField used to be a plain Select over Client.objects.all(), so
# the request form carried one <option> per person in the base, contacts of
# every firm included. It is now a hidden pk plus a search box; these lock the
# contract the Requests redesign has to keep (see crm/clients/fields.py).
import re

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from crm.clients.fields import ClientField
from crm.clients.models import Client, Company, CompanyPersonLink
from crm.zetom.models import RequestClientLink, RequestMain

BASE_REQ = {
    "first_name": "Jan",
    "last_name": "Kowalski",
    "phone": "+48501600300",
    "email": "jan@zetom.pl",
    "company_name": "Zetom",
}


class ClientPickerWidgetTest(TestCase):
    def test_renders_no_options_regardless_of_base_size(self):
        company = Company.objects.create(name="Zetom", nip="1234563218")
        for i in range(30):
            person = Client.objects.create(first_name=f"Kontakt{i}")
            CompanyPersonLink.objects.create(company=company, person=person)
        html = ClientField().widget.render("client", None)
        self.assertNotIn("<option", html)
        self.assertNotIn("Kontakt0", html)

    # claude — requestmain_client_link.js reads getElementById("id_client")
    # .value to build the Link call; the hidden input keeps that id so the
    # linker JS and the client_card partial needed no changes at all.
    def test_hidden_input_keeps_the_id_the_linker_reads(self):
        html = ClientField().widget.render("client", 42)
        self.assertIn('id="id_client"', html)
        self.assertIn('name="client"', html)
        self.assertIn('value="42"', html)

    def test_visible_box_carries_the_js_hook(self):
        html = ClientField().widget.render("client", None)
        self.assertIn("data-client-picker", html)
        self.assertIn('data-target="id_client"', html)

    # claude — the field is form-only and optional; the pk still has to resolve
    # to a real Client when one is submitted.
    def test_field_still_resolves_a_submitted_pk(self):
        person = Client.objects.create(first_name="Jan")
        field = ClientField()
        self.assertEqual(field.clean(str(person.pk)), person)
        self.assertIsNone(field.clean(""))


class RequestFormPickerTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("staff", "s@s.pl", "pass12345")
        self.client.force_login(self.user)
        self.company = Company.objects.create(name="Zetom", nip="1234563218")
        for i in range(30):
            person = Client.objects.create(first_name=f"Kontakt{i}")
            CompanyPersonLink.objects.create(company=self.company, person=person)

    def test_request_form_no_longer_lists_every_client(self):
        resp = self.client.get(
            reverse("admin:zetom_requestmain_add"), HTTP_HOST="127.0.0.1",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertNotIn("Kontakt0", body)
        self.assertIsNone(re.search(r'<select[^>]*name="client"', body))
        self.assertIn("data-client-picker", body)

    def test_picker_js_is_loaded(self):
        resp = self.client.get(
            reverse("admin:zetom_requestmain_add"), HTTP_HOST="127.0.0.1",
        )
        self.assertContains(resp, "client/client_picker.js")

    # claude — the picker feeds the "Link" button, which is the only way to
    # attach an existing client to a request. Exercised through the same admin
    # endpoint the button posts to.
    def test_linking_a_picked_client_still_works(self):
        person = Client.objects.create(first_name="Anna", last_name="Nowak")
        request_main = RequestMain.objects.create(**BASE_REQ)
        resp = self.client.post(
            reverse(
                "admin:zetom_requestmain_link_client_json",
                args=[request_main.pk, person.pk],
            ),
            HTTP_HOST="127.0.0.1",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        self.assertTrue(
            RequestClientLink.objects.filter(request=request_main, client=person).exists()
        )
