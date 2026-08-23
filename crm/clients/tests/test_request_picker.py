# claude — the "Powiąż zgłoszenie" picker behind the Add Client modal.
# Both endpoints narrow themselves to RequestMain when kind=firma, because a
# Company can only be attached through RequestMain.company (the child documents
# have no such FK).
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from crm.status_manager.services.statuses import RequestStatus
from crm.zetom.models import Oferta, RequestMain, Wniosek, Zlecenie

BASE_REQ = {
    "first_name": "Jan",
    "last_name": "Kowalski",
    "phone": "+48501600300",
    "email": "jan@zetom.pl",
    "company_name": "Zetom",
}


class RequestPickerTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("staff", "s@s.pl", "pass12345")
        self.client.force_login(self.user)
        self.suggest_url = reverse("admin:clients_client_request_suggest")
        self.search_url = reverse("admin:clients_client_request_search")
        for model in (RequestMain, Oferta, Zlecenie, Wniosek):
            model.objects.create(**BASE_REQ)

    def _suggest(self, **params):
        return self.client.get(self.suggest_url, params, HTTP_HOST="127.0.0.1").json()

    def _search(self, **params):
        return self.client.get(self.search_url, params, HTTP_HOST="127.0.0.1").json()

    def test_suggest_matches_on_contact(self):
        data = self._suggest(kind="osoba", phone="+48501600300")
        self.assertTrue(data["suggested"])
        self.assertTrue(all(r["match"] for r in data["suggested"]))

    def test_suggest_without_contact_returns_recent_only(self):
        data = self._suggest(kind="osoba")
        self.assertEqual(data["suggested"], [])
        self.assertTrue(data["recent"])

    def test_suggest_for_firma_offers_only_zgloszenia(self):
        data = self._suggest(kind="firma", phone="+48501600300")
        rows = data["suggested"] + data["recent"]
        self.assertTrue(rows)
        self.assertEqual({r["type"] for r in rows}, {"main"})

    def test_suggest_for_osoba_offers_every_type(self):
        data = self._suggest(kind="osoba", phone="+48501600300")
        rows = data["suggested"] + data["recent"]
        self.assertEqual({r["type"] for r in rows}, {"main", "oferta", "zlecenie", "wniosek"})

    def test_search_by_company_name(self):
        data = self._search(kind="osoba", q="Zetom")
        self.assertTrue(data["results"])
        self.assertEqual(data["total"], 4)

    def test_search_for_firma_is_narrowed(self):
        data = self._search(kind="firma", q="Zetom")
        self.assertEqual(data["total"], 1)
        self.assertEqual({r["type"] for r in data["results"]}, {"main"})

    def test_search_without_query_is_empty(self):
        self.assertEqual(self._search(kind="osoba", q="")["results"], [])

    # claude — cancelled/deleted requests stay out of both lists.
    def test_dead_requests_are_hidden(self):
        RequestMain.objects.update(status=RequestStatus.deleted)
        data = self._search(kind="firma", q="Zetom")
        self.assertEqual(data["total"], 0)

    def test_requires_view_permission(self):
        self.client.logout()
        viewer = User.objects.create_user("viewer", "v@v.pl", "pass12345", is_staff=True)
        profile = viewer.profile
        profile.otp_exempt = True
        profile.role = None
        profile.save()
        self.client.force_login(viewer)
        resp = self.client.get(self.search_url, {"q": "Zetom"}, HTTP_HOST="127.0.0.1")
        self.assertEqual(resp.status_code, 403)
