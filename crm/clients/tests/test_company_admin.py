# claude
from django.contrib import admin
from django.test import TestCase

from crm.clients.models import Company


class CompanyAdminRegisteredTest(TestCase):
    def test_company_registered(self):
        self.assertIn(Company, admin.site._registry)

    def test_company_admin_has_contact_inline(self):
        model_admin = admin.site._registry[Company]
        inline_models = [inline.model for inline in model_admin.inlines]
        from crm.clients.models import CompanyPersonLink
        self.assertIn(CompanyPersonLink, inline_models)
