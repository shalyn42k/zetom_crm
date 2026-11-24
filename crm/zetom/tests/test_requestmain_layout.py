# claude
"""RequestMain change page after the declutter redesign: actions are small
header buttons, history opens in a modal, departments sit in the team card."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from crm.zetom.models import RequestMain

User = get_user_model()

DOC = {
    "first_name": "Jan", "last_name": "Kowalski", "phone": "+48501600300",
    "email": "jan@client.pl", "company_name": "Acme", "departments": ["DEPARTMENT_0"],
}


class RequestMainLayoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("boss", "b@zetom.pl", "x")
        self.req = RequestMain.objects.create(**DOC)
        self.client.force_login(self.user)
        self.html = self.client.get(reverse("admin:zetom_requestmain_change", args=[self.req.pk])).content.decode()

    def test_toolbar_in_header(self):
        header = self.html[self.html.index('<header class="rm-header">'):self.html.index("</header>", self.html.index('<header class="rm-header">'))]
        for label in ("rm-toolbar", "open-step-notes", "historyOpen = true", "openReview()", "openMail()", "/cancel/"):
            self.assertIn(label, header)
        self.assertIn('form="requestmain_form" name="_continue"', header)

    def test_old_cards_gone(self):
        self.assertNotIn('id="rm-actions-heading"', self.html)
        self.assertNotIn('id="rm-dept-heading"', self.html)  # departments card
        self.assertIn('class="rm-team-depts"', self.html)    # now inside the team card
        self.assertIn("historyOpen", self.html)
        self.assertNotIn('id="submit-row"', self.html)       # bottom save row only on add

    def test_add_page_keeps_submit_row(self):
        html = self.client.get(reverse("admin:zetom_requestmain_add")).content.decode()
        self.assertIn('id="submit-row"', html)
        self.assertNotIn("rm-toolbar", html)

    def test_save_from_header_button_still_works(self):
        response = self.client.post(
            reverse("admin:zetom_requestmain_change", args=[self.req.pk]),
            {
                "first_name": "Jan", "last_name": "Nowak", "phone": "+48501600300", "email": "jan@client.pl",
                "company_name": "Acme", "company_nip": "", "address": "", "message": "", "source": self.req.source,
                "_continue": "1",
            },
        )
        self.assertEqual(response.status_code, 302, response.context and response.context["adminform"].form.errors)
        self.req.refresh_from_db()
        self.assertEqual(self.req.last_name, "Nowak")

    # claude — the old |length|add:|length chain always rendered 0
    def test_documents_counter_counts(self):
        from crm.zetom.models import Oferta, Zlecenie
        Oferta.objects.create(from_main=self.req, **DOC)
        Zlecenie.objects.create(from_main=self.req, **DOC)
        response = self.client.get(reverse("admin:zetom_requestmain_change", args=[self.req.pk]))
        self.assertEqual(response.context["docs_count"], 2)
        self.assertContains(response, '<span class="rm-counter">2</span>', html=False)

    # claude — linked clients as contact rows with real buttons
    def test_linked_client_row(self):
        from crm.clients.models import Client
        from crm.zetom.models import RequestClientLink
        cl = Client.objects.create(first_name="Anna", last_name="Lis", email="anna@acme.pl", phone="+48501600301")
        RequestClientLink.objects.create(request=self.req, client=cl, linked_by=self.user)
        html = self.client.get(reverse("admin:zetom_requestmain_change", args=[self.req.pk])).content.decode()
        self.assertIn('class="rm-linked-ava"', html)
        self.assertIn("anna@acme.pl", html)
        self.assertIn('class="rm-tbtn js-edit-client"', html)
        self.assertIn('class="rm-tbtn rm-tbtn--danger js-unlink-client"', html)
        self.assertIn('id="rm-linked-empty" hidden', html)

    def test_empty_state_offers_link_button(self):
        self.assertIn("js-open-link", self.html)
        self.assertNotIn('id="rm-linked-empty" hidden', self.html)

    def test_link_json_returns_contact(self):
        from crm.clients.models import Client
        cl = Client.objects.create(first_name="Ewa", last_name="Bąk", email="ewa@acme.pl")
        data = self.client.post(reverse("admin:zetom_requestmain_link_client_json", args=[self.req.pk, cl.pk])).json()
        self.assertEqual(data["email"], "ewa@acme.pl")
        self.assertIn("phone", data)

    # claude — searchable selects and grouped documents
    def test_team_selects_are_searchable(self):
        User.objects.create_user("extra", "e@zetom.pl", "x", is_staff=True)
        html = self.client.get(reverse("admin:zetom_requestmain_change", args=[self.req.pk])).content.decode()
        self.assertIn('name="user_id" class="rm-select" data-combobox', html)
        self.assertIn('name="dept_code" class="rm-select" data-combobox', html)

    def test_documents_grouped_with_links(self):
        from crm.zetom.models import Oferta
        o = Oferta.objects.create(from_main=self.req, **DOC)
        html = self.client.get(reverse("admin:zetom_requestmain_change", args=[self.req.pk])).content.decode()
        self.assertIn('class="rm-dgroup__doc" href="%s"' % reverse("admin:zetom_oferta_change", args=[o.pk]), html)
        self.assertIn(reverse("admin:zetom_requestmain_oferta_action", args=[self.req.pk]), html)
