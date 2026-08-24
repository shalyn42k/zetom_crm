# claude — the dashboard's "Clients" tile links to the Klienci list, so its
# number has to be that list's total. The invariant is the point of this file;
# what the list shows has changed twice. It first excluded a firm's contacts,
# so the tile had to as well. The list now shows every person, contacts
# included, so the tile counts them again — the two must not drift apart.
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from crm.clients.models import Client, Company, CompanyPersonLink
from crm.users.templatetags.admin_dashboard import dashboard_summary


class DashboardClientsCountTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("staff", "s@s.pl", "pass12345")
        self.client.force_login(self.user)
        company = Company.objects.create(name="Zetom", nip="1234563218")
        for i in range(5):
            contact = Client.objects.create(first_name=f"Kontakt{i}")
            CompanyPersonLink.objects.create(company=company, person=contact)
        Client.objects.create(first_name="Prywatny")

    def test_tile_matches_the_list_it_links_to(self):
        resp = self.client.get(
            reverse("admin:clients_client_changelist"), HTTP_HOST="127.0.0.1",
        )
        self.assertEqual(
            dashboard_summary(self.user)["clients"], resp.context["counts"]["all"],
        )

    def test_contacts_are_counted_as_clients(self):
        # one firm + five contacts + one private person, all visible in the list
        self.assertEqual(dashboard_summary(self.user)["clients"], 7)
        self.assertEqual(Client.objects.count(), 6)

    def test_hidden_without_permission(self):
        viewer = User.objects.create_user("viewer", "v@v.pl", "pass12345", is_staff=True)
        profile = viewer.profile
        profile.role = None
        profile.save()
        self.assertEqual(dashboard_summary(viewer)["clients"], 0)
