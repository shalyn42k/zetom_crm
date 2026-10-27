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
        self.assertContains(response, 'data-de-field="price"')
        self.assertContains(response, "Two audits")
        self.assertContains(response, reverse("admin:zetom_oferta_print", args=[self.oferta.pk]))
        self.assertContains(response, reverse("admin:zetom_oferta_mark_done", args=[self.oferta.pk]))
        self.assertContains(response, reverse("admin:zetom_requestmain_change", args=[self.parent.pk]))

    def test_form_shows_only_template_and_client_fields(self):
        response = self._change(self.oferta)
        rendered = {f for fs in response.context["adminform"] for line in fs for f in line.fields}
        self.assertTrue({"price", "notes", "first_name", "company_nip", "email", "phone"} <= rendered)
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
            "price": "1500", "notes": "Updated", "first_name": "Jan", "last_name": "Kowalski",
            "company_name": "Acme", "company_nip": "", "email": "jan@client.pl",
            "phone": "+48501600300", "_continue": "1",
        })
        self.assertEqual(response.status_code, 302, response.content[:3000])
        self.oferta.refresh_from_db()
        self.assertEqual(str(self.oferta.price), "1500.00")
        self.assertEqual(self.oferta.notes, "Updated")
        # fields no longer on the form keep their values
        self.assertEqual(self.oferta.departments, ["DEPARTMENT_0"])
        self.assertEqual(list(self.oferta.assigned_to.all()), [self.user])

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
