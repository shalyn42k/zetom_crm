# claude — a view-only role (auditor) opening a request: Django drops the
# model fields from the admin form, so the "Client information" card lost
# first/last name (crispy logged KeyError) and showed the remaining
# declared fields as empty, editable inputs.
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from crm.users.models import Role
from crm.zetom.models import RequestMain

_SIMPLE_STATIC = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(STORAGES=_SIMPLE_STATIC, CRISPY_FAIL_SILENTLY=False)
class ViewOnlyRequestCardTests(TestCase):
    def setUp(self):
        self.auditor = User.objects.create_user("aud", "aud@zetom.pl", "x", is_staff=True)
        profile = self.auditor.profile
        profile.role = Role.objects.get(code="auditor")
        profile.departments = ["DEPARTMENT_0"]
        profile.otp_exempt = True
        profile.save()
        self.req = RequestMain.objects.create(
            first_name="Jan", last_name="Kowalski", phone="+48501600300",
            email="jan@client.pl", company_name="Acme", departments=["DEPARTMENT_0"],
        )
        self.req.assigned_to.add(self.auditor)
        self.client.force_login(self.auditor)

    def test_auditor_sees_client_data_read_only(self):
        response = self.client.get(reverse("admin:zetom_requestmain_change", args=[self.req.pk]))
        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        for name, value in (("first_name", "Jan"), ("last_name", "Kowalski"), ("email", "jan@client.pl")):
            self.assertIn(name, form.fields)
            self.assertTrue(form.fields[name].disabled, name)
            self.assertEqual(form[name].value(), value)
