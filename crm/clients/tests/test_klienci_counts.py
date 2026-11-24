# claude — the list's "Zgłoszenia" column counted RequestMain only, while the
# Person card's header counted all four document types, so the same person
# showed two different numbers depending on which screen you were on.
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from crm.clients.models import Client
from crm.clients.services import get_client_request_summary
from crm.status_manager.services.statuses import RequestStatus
from crm.zetom.models import Oferta, RequestMain, Wniosek, Zlecenie

BASE_DATA = {
    "first_name": "Jan",
    "last_name": "Prywatny",
    "phone": "+48501600300",
    "email": "jan@zetom.pl",
    "company_name": "Zetom",
}


class ZgloszeniaCountTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("staff", "s@s.pl", "pass12345")
        self.client.force_login(self.user)
        self.person = Client.objects.create(first_name="Jan", last_name="Prywatny")
        for model in (RequestMain, Oferta, Zlecenie, Wniosek):
            obj = model.objects.create(**BASE_DATA)
            obj.clients.add(self.person)

    def _row(self):
        resp = self.client.get(
            reverse("admin:clients_client_changelist"), HTTP_HOST="127.0.0.1",
        )
        return resp.context["rows"][0]

    def test_list_column_matches_card_summary(self):
        summary_total = sum(get_client_request_summary(self.person).values())
        self.assertEqual(summary_total, 4)
        self.assertEqual(self._row()["zgloszenia_count"], summary_total)

    # claude — four distinct counts, not one summed aggregate: joining four
    # M2Ms in a single expression multiplies rows and inflates every count.
    def test_count_is_not_inflated_by_joins(self):
        second = RequestMain.objects.create(**BASE_DATA)
        second.clients.add(self.person)
        self.assertEqual(self._row()["zgloszenia_count"], 5)

    def test_cancelled_requests_excluded(self):
        dead = RequestMain.objects.create(**BASE_DATA, status=RequestStatus.cancelled)
        dead.clients.add(self.person)
        self.assertEqual(self._row()["zgloszenia_count"], 4)
