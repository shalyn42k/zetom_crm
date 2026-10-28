# claude
"""Client data flow: linked client -> request "Client information" ->
document, the "where is the data from" log on the document, and sending
the finished document to the client."""
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from crm.clients.models import Client, Company, CompanyPersonLink
from crm.status_manager.services.statuses import Status
from crm.zetom.models import (
    Oferta, RequestAttachment, RequestClientLink, RequestMain, StepNote,
    Zlecenie,
)

User = get_user_model()


class ClientFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("boss", "b@zetom.pl", "x", first_name="Anna", last_name="Nowak")
        self.client.force_login(self.user)
        self.req = RequestMain.objects.create(phone="+48501600300", email="jan@acme.pl", source="email")
        self.req.assigned_to.add(self.user)
        self.person = Client.objects.create(first_name="Jan", last_name="Kowalski", email="jan@acme.pl", phone="+48501600301")
        self.company = Company.objects.create(name="Acme Sp. z o.o.", nip="1234563218", street="ul. Przemysłowa 12",
                                              post_code="00-001", city="Warszawa")
        CompanyPersonLink.objects.create(company=self.company, person=self.person)

    def tearDown(self):
        for a in RequestAttachment.objects.all():
            a.file.delete(save=False)

    def test_linking_fills_only_empty_request_fields(self):
        self.req.last_name = "Ręcznie"
        self.req.save()
        data = self.client.post(reverse("admin:zetom_requestmain_link_client_json", args=[self.req.pk, self.person.pk])).json()
        self.req.refresh_from_db()
        self.assertEqual(self.req.first_name, "Jan")
        self.assertEqual(self.req.last_name, "Ręcznie")          # typed value kept
        self.assertEqual(self.req.company_name, "Acme Sp. z o.o.")
        self.assertEqual(self.req.company_nip, "1234563218")
        self.assertEqual(self.req.address, "ul. Przemysłowa 12, 00-001 Warszawa")
        self.assertEqual(self.req.email, "jan@acme.pl")           # already set, untouched
        self.assertIn("company_nip", data["filled"])
        self.assertNotIn("last_name", data["filled"])
        # the client base is not written to by request edits
        self.req.company_name = "Inna nazwa"
        self.req.save()
        self.company.refresh_from_db()
        self.assertEqual(self.company.name, "Acme Sp. z o.o.")

    def test_client_information_shows_company_fields(self):
        html = self.client.get(reverse("admin:zetom_requestmain_change", args=[self.req.pk])).content.decode()
        self.assertEqual(html.count('name="company_nip"'), 1)    # once — not also in the link dialog
        self.assertEqual(html.count('name="first_name"'), 1)

    def test_new_document_gets_the_request_copy_and_opens(self):
        self.req.first_name, self.req.last_name, self.req.company_name = "Jan", "Kowalski", "Acme"
        self.req.save()
        RequestClientLink.objects.create(request=self.req, client=self.person, linked_by=self.user)
        response = self.client.post(reverse("admin:zetom_requestmain_oferta_action", args=[self.req.pk]))
        oferta = Oferta.objects.get()
        self.assertRedirects(response, reverse("admin:zetom_oferta_change", args=[oferta.pk]), fetch_redirect_response=False)
        self.assertEqual((oferta.first_name, oferta.last_name, oferta.company_name), ("Jan", "Kowalski", "Acme"))
        self.assertEqual(list(oferta.clients.all()), [self.person])
        self.assertEqual(oferta.inquiry_channel, "email")
        self.assertIsNotNone(oferta.inquiry_date)
        response = self.client.post(reverse("admin:zetom_requestmain_zlecenie_action", args=[self.req.pk]))
        self.assertRedirects(response, reverse("admin:zetom_zlecenie_change", args=[Zlecenie.objects.get().pk]),
                             fetch_redirect_response=False)


class DocumentSourceAndSendTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("boss", "b@zetom.pl", "x", first_name="Anna", last_name="Nowak")
        self.client.force_login(self.user)
        self.oferta = Oferta.objects.create(first_name="Jan", last_name="Kowalski", phone="+48501600300",
                                            email="jan@acme.pl", company_name="Acme", offer_number="LTO/1/2025-10")
        self.oferta.assigned_to.add(self.user)
        self.url = reverse("admin:zetom_oferta_change", args=[self.oferta.pk])

    def tearDown(self):
        for a in RequestAttachment.objects.all():
            a.file.delete(save=False)

    def _post(self, **extra):
        data = {
            "offer_number": "LTO/1/2025-10", "offer_date": "", "subject": "wzorcowania", "inquiry_channel": "email",
            "inquiry_date": "", "extra_costs": "", "vat_rate": "23", "place_of_work": "", "completion_term": "",
            "confirmation_document": "", "payment_terms": "", "notes": "",
            "first_name": "Jan", "last_name": "Kowalski", "company_name": "Acme", "company_nip": "",
            "email": "jan@acme.pl", "phone": "+48501600300",
            "items-TOTAL_FORMS": "0", "items-INITIAL_FORMS": "0", "items-MIN_NUM_FORMS": "0", "items-MAX_NUM_FORMS": "1000",
            "_continue": "1",
        }
        data.update(extra)
        return self.client.post(self.url, data)

    def test_changed_client_data_needs_a_source(self):
        response = self._post(company_name="Acme Polska")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "contact log")
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.company_name, "Acme")

    def test_source_given_saves_and_logs(self):
        response = self._post(company_name="Acme Polska", source_channel="call", source_person="Anna z księgowości",
                              source_note="Podała nową nazwę")
        self.assertEqual(response.status_code, 302)
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.company_name, "Acme Polska")
        note = StepNote.objects.get()
        self.assertEqual(note.kind, "contact")
        self.assertEqual(note.channel, "call")
        self.assertEqual(note.contact_person, "Anna z księgowości")
        self.assertEqual(note.target, self.oferta)

    def test_other_edits_need_no_source(self):
        response = self._post(completion_term="listopad 2025 r.")
        self.assertEqual(response.status_code, 302)
        self.assertFalse(StepNote.objects.exists())

    def test_send_to_client(self):
        response = self.client.post(reverse("admin:zetom_oferta_send_to_client", args=[self.oferta.pk]),
                                    {"to": "jan@acme.pl", "subject": "Oferta LTO/1/2025-10", "message": "Dzień dobry"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)                    # no extra "in progress" mail
        sent = mail.outbox[0]
        self.assertEqual(sent.to, ["jan@acme.pl"])
        self.assertIn("LTO/1/2025-10", sent.alternatives[0][0])
        self.assertEqual(sent.alternatives[0][1], "text/html")
        self.assertEqual(len(sent.attachments), 1)
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.status, Status.waiting)
        self.assertTrue(RequestAttachment.objects.filter(oferta=self.oferta, file__contains="wyslane").exists())
        self.assertEqual(StepNote.objects.get().channel, "email")

    def test_send_only_to_known_address(self):
        self.client.post(reverse("admin:zetom_oferta_send_to_client", args=[self.oferta.pk]),
                         {"to": "x@evil.example", "subject": "s", "message": "m"})
        self.assertEqual(len(mail.outbox), 0)
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.status, Status.new)
