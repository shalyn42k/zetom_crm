# claude — /admin/clients/ is Django's app index: a bare page listing the three
# registered models. Unfold links it from the breadcrumbs on every clients
# screen, so "back" from a card landed users on a three-way choice instead of
# the list. Redirected to the unified Klienci list (config/urls.py).
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from crm.clients.models import Client, Company


class AppIndexRedirectTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("staff", "s@s.pl", "pass12345")
        self.client.force_login(self.user)

    def test_app_index_redirects_to_list(self):
        resp = self.client.get("/admin/clients/", HTTP_HOST="127.0.0.1")
        self.assertRedirects(
            resp, reverse("admin:clients_client_changelist"), fetch_redirect_response=False,
        )

    # claude — the redirect is an exact-path match, so nothing underneath it
    # (the changelist, the cards, every JSON endpoint) may be swallowed.
    def test_deeper_admin_urls_still_resolve(self):
        person = Client.objects.create(first_name="Jan")
        company = Company.objects.create(name="Zetom")
        for url in (
            reverse("admin:clients_client_changelist"),
            reverse("admin:clients_client_change", args=[person.pk]),
            reverse("admin:clients_company_change", args=[company.pk]),
        ):
            with self.subTest(url=url):
                self.assertEqual(
                    self.client.get(url, HTTP_HOST="127.0.0.1").status_code, 200,
                )

    # claude — the stock Company changelist is the raw checkbox table the
    # Klienci list replaced; Unfold links it from the breadcrumbs, so the URL
    # itself has to redirect, not just the two links we control.
    def test_company_changelist_redirects_to_the_firms_filter(self):
        resp = self.client.get("/admin/clients/company/", HTTP_HOST="127.0.0.1")
        self.assertRedirects(
            resp,
            reverse("admin:clients_client_changelist") + "?rodzaj=firmy",
            fetch_redirect_response=False,
        )

    def test_no_page_links_the_old_company_list(self):
        company = Company.objects.create(name="Zetom")
        pages = [
            reverse("admin:index"),
            reverse("admin:clients_client_changelist"),
            reverse("admin:clients_company_change", args=[company.pk]),
        ]
        for url in pages:
            with self.subTest(url=url):
                body = self.client.get(url, HTTP_HOST="127.0.0.1").content.decode()
                self.assertNotIn('href="/admin/clients/company/"', body)

    # claude — Unfold's header_title builds the "Clients › Companies › …" chain
    # from `opts`, so the designed pages leave it out of their context: the
    # chain's links point at the stock screens these pages replaced, and each
    # page carries its own header and "Wróć". The redirects above stay as the
    # guard for anyone arriving by a typed or bookmarked URL.
    def test_designed_pages_render_no_app_chain(self):
        person = Client.objects.create(first_name="Jan")
        company = Company.objects.create(name="Zetom")
        pages = [
            reverse("admin:clients_client_changelist"),
            reverse("admin:clients_client_change", args=[person.pk]),
            reverse("admin:clients_company_change", args=[company.pk]),
        ]
        for url in pages:
            with self.subTest(url=url):
                body = self.client.get(url, HTTP_HOST="127.0.0.1").content.decode()
                self.assertNotIn('href="/admin/clients/"', body)
