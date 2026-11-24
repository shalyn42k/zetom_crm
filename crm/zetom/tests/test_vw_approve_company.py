# claude
from django.contrib.auth.models import User
from django.test import TestCase

from crm.clients.models import Client, Company, CompanyPersonLink
from crm.zetom.admin.requestnull_validate import _do_approve
from crm.zetom.models import DepartmentsVariants, RequestNull


class VWApproveCompanyTest(TestCase):
    def _cleaned(self, **over):
        base = {
            "departments": [DepartmentsVariants.choices[0][0]],
            "owners": [],
            "link_client_ids": [],
            "create_new": True,
            "new_first_name": "Jan",
            "new_last_name": "Kowalski",
            "new_phone": "+48501600300",
            "new_email": "jan@zetom.pl",
            "new_company_name": "Zetom",
            "new_company_nip": "1234563218",
        }
        base.update(over)
        return base

    def test_approve_creates_company_and_sets_requestmain_company(self):
        rn = RequestNull.objects.create(
            first_name="Jan", last_name="Kowalski",
            phone="+48501600300", email="jan@zetom.pl", company_name="Zetom",
        )
        user = User.objects.create(username="validator")
        new_main = _do_approve(rn, self._cleaned(), user=user)

        company = Company.objects.get(nip="1234563218")
        self.assertEqual(new_main.company_id, company.pk)
        person = Client.objects.get(first_name="Jan")
        # claude — company-данные живут на Company + CompanyPersonLink, не на
        # Client (Client.company_* дропнуты в phase 2c).
        self.assertEqual(CompanyPersonLink.objects.filter(company=company, person=person).count(), 1)
