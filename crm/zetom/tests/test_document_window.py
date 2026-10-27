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
        self.oferta = Oferta.objects.create(from_main=self.parent, price="1200.00", notes="Two audits", **DOC)
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
        self.assertContains(response, 'data-de-field="price"')
        self.assertContains(response, "Two audits")
        self.assertContains(response, reverse("admin:zetom_oferta_print", args=[self.oferta.pk]))
        self.assertContains(response, reverse("admin:zetom_oferta_mark_done", args=[self.oferta.pk]))
        self.assertContains(response, reverse("admin:zetom_requestmain_change", args=[self.parent.pk]))

    def test_form_keeps_only_template_fields_up_front(self):
        response = self._change(self.oferta)
        form = response.context["adminform"].form
        for name in ("price", "notes", "first_name", "company_nip", "email", "phone", "departments", "assigned_to", "source"):
            self.assertIn(name, form.fields)

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
            "price": "1500", "notes": "Updated", "first_name": "Jan", "last_name": "Kowalski",
            "company_name": "Acme", "company_nip": "", "email": "jan@client.pl",
            "phone": "+48501600300", "source": self.oferta.source, "_continue": "1",
        })
        self.assertEqual(response.status_code, 302, response.content[:3000])
        self.oferta.refresh_from_db()
        self.assertEqual(str(self.oferta.price), "1500.00")
        self.assertEqual(self.oferta.notes, "Updated")

    def test_print_page(self):
        response = self.client.get(reverse("admin:zetom_oferta_print", args=[self.oferta.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, document_code(self.oferta))
        self.assertContains(response, "window.print()")
        self.assertContains(response, "1200")

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
