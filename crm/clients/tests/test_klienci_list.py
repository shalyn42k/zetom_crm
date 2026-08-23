# claude
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from crm.clients.models import Client, Company, CompanyPersonLink


class KlienciListTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("staff", "s@s.pl", "pass12345")
        self.client.force_login(self.user)
        self.firma = Company.objects.create(name="Zetom Sp.", nip="1234563218")
        self.osoba = Client.objects.create(first_name="Jan", last_name="Prywatny")  # no links = private
        linked = Client.objects.create(first_name="Anna", last_name="Kontakt")
        CompanyPersonLink.objects.create(company=self.firma, person=linked)  # contact, not private

    def _get(self, **params):
        return self.client.get(reverse("admin:clients_client_changelist"), params, HTTP_HOST="127.0.0.1")

    def test_list_shows_company_and_private_person(self):
        resp = self._get()
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Zetom Sp.")       # firma
        self.assertContains(resp, "Jan Prywatny")     # private person
        self.assertContains(resp, "Private person")  # EN locale (LANGUAGE_CODE=en)

    # claude — assert on the built rows, not on raw HTML: the Add Client modal
    # ships example placeholders ("np. Zetom Sp. z o.o.") that collide with
    # company names in an assertNotContains over the whole page.
    def test_filter_firmy_only(self):
        rows = self._get(rodzaj="firmy").context["rows"]
        self.assertEqual([r["nazwa"] for r in rows], ["Zetom Sp."])

    def test_filter_osoby_only(self):
        rows = self._get(rodzaj="osoby").context["rows"]
        self.assertEqual([r["nazwa"] for r in rows], ["Jan Prywatny"])


# claude — the merged list used to be "all companies sorted, then all persons
# sorted", so with more companies than fit on a page no private person was
# reachable until the last pages. Rows are now globally ordered by name.
class KlienciListOrderingTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("staff", "s@s.pl", "pass12345")
        self.client.force_login(self.user)
        Company.objects.create(name="Beta Sp.")
        Company.objects.create(name="Delta Sp.")
        Client.objects.create(first_name="Alfa", last_name="Osoba")
        Client.objects.create(first_name="Cezary", last_name="Osoba")

    def test_rows_are_interleaved_alphabetically(self):
        resp = self.client.get(
            reverse("admin:clients_client_changelist"), HTTP_HOST="127.0.0.1",
        )
        names = [row["nazwa"] for row in resp.context["rows"]]
        self.assertEqual(names, ["Alfa Osoba", "Beta Sp.", "Cezary Osoba", "Delta Sp."])

    def test_counts_cover_both_kinds(self):
        resp = self.client.get(
            reverse("admin:clients_client_changelist"), HTTP_HOST="127.0.0.1",
        )
        self.assertEqual(resp.context["counts"], {"all": 4, "firmy": 2, "osoby": 2})

    # claude — only the current page's objects get fetched and shaped now; the
    # merge itself runs on (pk, name) tuples.
    def test_page_builds_only_its_own_rows(self):
        for i in range(30):
            Company.objects.create(name=f"Firma {i:02d}")
        resp = self.client.get(
            reverse("admin:clients_client_changelist"), HTTP_HOST="127.0.0.1",
        )
        self.assertEqual(len(resp.context["rows"]), 25)
        self.assertEqual(resp.context["paginator"].count, 34)
