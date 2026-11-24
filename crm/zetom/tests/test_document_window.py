# claude
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from crm.notification.services.request_mail import document_code
from crm.zetom.models import Oferta, RequestMain, Wniosek, Zlecenie

User = get_user_model()

DOC = {
    "first_name": "Jan", "last_name": "Kowalski",
    "phone": "+48501600300", "email": "jan@client.pl", "company_name": "Acme",
}


class DocumentWindowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="spec", password="x", is_staff=True)
        self.parent = RequestMain.objects.create(**DOC)
        self.oferta = Oferta.objects.create(
            from_main=self.parent, price="1200.00", notes="Two audits", departments=["DEPARTMENT_0"], **DOC,
        )
        self.zlecenie = Zlecenie.objects.create(from_main=self.parent, **DOC)
        self.wniosek = Wniosek.objects.create(from_main=self.parent, application_number="W/1/2026", **DOC)
        for obj in (self.parent, self.oferta, self.zlecenie, self.wniosek):
            obj.assigned_to.add(self.user)
        self.client.force_login(self.user)

    def _change(self, obj):
        return self.client.get(reverse(f"admin:zetom_{type(obj).__name__.lower()}_change", args=[obj.pk]))

    def test_oferta_window_has_preview_and_print(self):
        response = self._change(self.oferta)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "de-paper")
        self.assertContains(response, document_code(self.oferta))
        self.assertContains(response, 'data-de-field="offer_number"')
        self.assertContains(response, "data-de-items-body")
        self.assertContains(response, reverse("admin:zetom_oferta_print", args=[self.oferta.pk]))
        self.assertContains(response, reverse("admin:zetom_oferta_mark_done", args=[self.oferta.pk]))
        self.assertContains(response, reverse("admin:zetom_requestmain_change", args=[self.parent.pk]))

    def test_form_shows_only_template_and_client_fields(self):
        response = self._change(self.oferta)
        rendered = {f for fs in response.context["adminform"] for line in fs for f in line.fields}
        self.assertTrue({"offer_number", "offer_date", "inquiry_channel", "inquiry_date", "subject", "payment_terms",
                         "notes", "first_name", "company_nip", "email", "phone"} <= rendered)
        self.assertNotIn("price", rendered)  # computed from the items
        self.assertTrue(rendered.isdisjoint({"departments", "assigned_to", "source", "from_main"}))

    def test_zlecenie_has_no_manual_done(self):
        response = self._change(self.zlecenie)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-de-field="deadline"')
        self.assertNotContains(response, "mark-done")

    def test_wniosek_shows_application_number(self):
        response = self._change(self.wniosek)
        self.assertContains(response, "W/1/2026")
        self.assertContains(response, 'data-de-field="application_number"')

    def test_save_still_works(self):
        url = reverse("admin:zetom_oferta_change", args=[self.oferta.pk])
        response = self.client.post(url, {
            "offer_number": "", "offer_date": "", "subject": "wzorcowania", "inquiry_channel": "email", "inquiry_date": "2025-10-28",
            "extra_costs": "150", "vat_rate": "23", "place_of_work": "w miejscu użytkowania",
            "completion_term": "listopad 2025 r.", "confirmation_document": "Świadectwo", "payment_terms": "14 dni",
            "notes": "Updated", "first_name": "Jan", "last_name": "Kowalski",
            "company_name": "Acme", "company_nip": "", "email": "jan@client.pl", "phone": "+48501600300",
            "items-TOTAL_FORMS": "1", "items-INITIAL_FORMS": "0", "items-MIN_NUM_FORMS": "0", "items-MAX_NUM_FORMS": "1000",
            "items-0-name": "Maszyna wytrzymałościowa", "items-0-details": "zakres 500kN", "items-0-norm": "PN-EN ISO 7500-1",
            "items-0-quantity": "1", "items-0-unit_price": "1200",
            "_continue": "1",
        })
        self.assertEqual(response.status_code, 302, response.content[:3000])
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.items.count(), 1)
        self.assertEqual(str(self.oferta.price), "1350.00")  # 1200 + 150 extra, net
        self.assertEqual(self.oferta.notes, "Updated")
        self.assertTrue(self.oferta.offer_number.startswith(f"LTO/{self.oferta.pk}/"))
        self.assertIsNotNone(self.oferta.offer_date)
        self.assertEqual(str(self.oferta.inquiry_date), "2025-10-28")
        # fields no longer on the form keep their values
        self.assertEqual(self.oferta.departments, ["DEPARTMENT_0"])
        self.assertEqual(list(self.oferta.assigned_to.all()), [self.user])

    def test_print_page(self):
        response = self.client.get(reverse("admin:zetom_oferta_print", args=[self.oferta.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, document_code(self.oferta))
        self.assertContains(response, "window.print()")
        self.assertContains(response, "Oferta numer")
        self.assertContains(response, "Warunki płatności")

    def test_print_page_hidden_document_is_404(self):
        stranger = User.objects.create_user(username="stranger", password="x", is_staff=True)
        hidden = Oferta.objects.create(**DOC)
        hidden.assigned_to.add(stranger)
        response = self.client.get(reverse("admin:zetom_oferta_print", args=[hidden.pk]))
        self.assertEqual(response.status_code, 404)

    def test_add_view_still_renders(self):
        response = self.client.get(reverse("admin:zetom_oferta_add"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "de-paper")


# claude
class DocumentFilesTests(TestCase):
    def setUp(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.Upload = SimpleUploadedFile
        self.user = User.objects.create_user(username="spec", password="x", is_staff=True)
        self.oferta = Oferta.objects.create(**DOC)
        self.oferta.assigned_to.add(self.user)
        self.client.force_login(self.user)

    def tearDown(self):
        from crm.zetom.models import RequestAttachment
        for att in RequestAttachment.objects.all():
            att.file.delete(save=False)

    def test_upload_list_download_delete(self):
        from crm.zetom.models import RequestAttachment

        self.client.post(
            reverse("admin:zetom_oferta_upload_files", args=[self.oferta.pk]),
            {"files": [self.Upload("kosztorys.txt", b"draft")]},
        )
        att = RequestAttachment.objects.get(oferta=self.oferta)
        self.assertEqual(att.uploaded_by, self.user)
        page = self.client.get(reverse("admin:zetom_oferta_change", args=[self.oferta.pk]))
        self.assertContains(page, att.download_url)
        download = self.client.get(att.download_url)
        self.assertEqual(download.status_code, 200)
        self.assertEqual(b"".join(download.streaming_content), b"draft")
        self.client.post(reverse("admin:zetom_oferta_delete_file", args=[self.oferta.pk, att.pk]))
        self.assertFalse(RequestAttachment.objects.exists())

    def test_create_document_saves_a_version(self):
        from crm.zetom.models import RequestAttachment

        url = reverse("admin:zetom_oferta_create_document", args=[self.oferta.pk])
        self.client.post(url)
        self.client.post(url)
        names = sorted(a.display_name for a in RequestAttachment.objects.filter(oferta=self.oferta))
        code = document_code(self.oferta).lower()
        self.assertEqual(names, [f"{code}-v1.html", f"{code}-v2.html"])
        content = RequestAttachment.objects.first().file.read().decode()
        self.assertIn(document_code(self.oferta), content)

    def test_download_needs_visibility(self):
        from crm.zetom.models import RequestAttachment

        att = RequestAttachment.objects.create(oferta=self.oferta, file=self.Upload("x.txt", b"x"), uploaded_by=self.user)
        stranger = User.objects.create_user(username="stranger", password="x", is_staff=True)
        self.client.force_login(stranger)
        self.assertEqual(self.client.get(att.download_url).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(att.download_url).status_code, 302)  # to login

    def test_upload_rejected_without_change_permission(self):
        from crm.users.models import Role
        Role.objects.get(code="specialist").permissions.filter(code="edit_requests").delete()
        response = self.client.post(
            reverse("admin:zetom_oferta_upload_files", args=[self.oferta.pk]),
            {"files": [self.Upload("a.txt", b"a")]},
        )
        self.assertEqual(response.status_code, 403)


# claude
class OfertaTotalsTests(TestCase):
    def test_totals_and_vat(self):
        from decimal import Decimal

        from crm.zetom.models import OfertaItem
        o = Oferta.objects.create(extra_costs=Decimal("150"), vat_rate=23, **DOC)
        OfertaItem.objects.create(oferta=o, name="A", quantity=2, unit_price=Decimal("600"))
        OfertaItem.objects.create(oferta=o, name="B", quantity=1, unit_price=None)
        self.assertEqual(o.items_total, Decimal("1200"))
        self.assertEqual(o.net_total, Decimal("1350"))
        self.assertEqual(o.vat_amount, Decimal("310.50"))
        self.assertEqual(o.gross_total, Decimal("1660.50"))


# claude
class OfertaWindowOptimisedTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("boss", "b@zetom.pl", "x")
        self.client.force_login(self.user)
        import datetime
        self.o = Oferta.objects.create(offer_number="LTO/987/2025-10", inquiry_channel="phone",
                                       inquiry_date=datetime.date(2025, 10, 28), **DOC)

    def test_dates_use_calendar_and_header_shows_offer_number(self):
        html = self.client.get(reverse("admin:zetom_oferta_change", args=[self.o.pk])).content.decode()
        self.assertIn('type="date" name="offer_date"', html)
        self.assertIn('type="date" name="inquiry_date" value="2025-10-28"', html)
        self.assertIn('<span class="de-bar__code">LTO/987/2025-10</span>', html)
        self.assertIn("zapytanie telefoniczne", html)  # Polish phrase on the sheet
        self.assertIn("28.10.2025", html)
