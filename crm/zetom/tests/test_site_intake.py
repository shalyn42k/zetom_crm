# claude — POST /zetom/api/site-request/: the client's WordPress site
# (zetomkatowice.eu, Divi contact form) forwards each submission here.
import json
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from crm.zetom.models import RequestNull, RequestSource

TOKEN = "test-intake-token"
URL_NAME = "zetom:site_request"

PAYLOAD = {
    "first_name": "Jan",
    "last_name": "Kowalski",
    "phone": "32 256 92 57",
    "email": "jan@firma.pl",
    "company_name": "Firma Sp. z o.o.",
    "message": "Prośba o wycenę wzorcowania.",
}


@override_settings(SITE_INTAKE_TOKEN=TOKEN)
@patch("crm.zetom.views.send_notification_to_staff")
class SiteIntakeTests(TestCase):
    def post(self, payload=PAYLOAD, token=TOKEN, **extra):
        headers = {"HTTP_AUTHORIZATION": f"Bearer {token}"} if token else {}
        return self.client.post(
            reverse(URL_NAME), data=json.dumps(payload),
            content_type="application/json", **headers, **extra,
        )

    def test_creates_validation_request_from_site(self, notify):
        response = self.post()
        self.assertEqual(response.status_code, 201)
        req = RequestNull.objects.get(pk=response.json()["id"])
        self.assertEqual(req.source, RequestSource.SITE)
        self.assertEqual((req.first_name, req.last_name, req.email), ("Jan", "Kowalski", "jan@firma.pl"))
        self.assertEqual(req.company_name, "Firma Sp. z o.o.")
        self.assertEqual(req.message, "Prośba o wycenę wzorcowania.")
        self.assertEqual(req.phone.as_e164, "+48322569257")
        notify.assert_called_once_with(req)

    def test_wrong_or_missing_token_is_rejected(self, notify):
        self.assertEqual(self.post(token="nope").status_code, 401)
        self.assertEqual(self.post(token=None).status_code, 401)
        self.assertFalse(RequestNull.objects.exists())

    @override_settings(SITE_INTAKE_TOKEN="")
    def test_disabled_when_token_not_configured(self, notify):
        self.assertEqual(self.post(token="").status_code, 404)
        self.assertEqual(self.post(token="anything").status_code, 404)

    def test_only_post(self, notify):
        response = self.client.get(reverse(URL_NAME), HTTP_AUTHORIZATION=f"Bearer {TOKEN}")
        self.assertEqual(response.status_code, 405)

    def test_invalid_data_returns_field_errors(self, notify):
        response = self.post({**PAYLOAD, "email": "not-an-email", "last_name": ""})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()["errors"]), {"email", "last_name"})
        self.assertFalse(RequestNull.objects.exists())

    def test_malformed_json_is_400(self, notify):
        response = self.client.post(
            reverse(URL_NAME), data="{not json", content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {TOKEN}",
        )
        self.assertEqual(response.status_code, 400)

    def test_client_id_in_payload_is_ignored(self, notify):
        from crm.clients.models import Client

        existing = Client.objects.create(first_name="Anna", last_name="Nowak", email="anna@x.pl")
        with patch("crm.zetom.views.AddRequestFormNull", wraps=__import__(
            "crm.zetom.forms", fromlist=["AddRequestFormNull"]).AddRequestFormNull) as form_cls:
            response = self.post({**PAYLOAD, "client": existing.pk, "status": "cancelled"})
        self.assertEqual(response.status_code, 201)
        self.assertNotIn("client", form_cls.call_args.args[0])
        req = RequestNull.objects.get(pk=response.json()["id"])
        self.assertEqual((req.first_name, req.status), ("Jan", "active"))

    def test_resubmission_within_window_does_not_duplicate(self, notify):
        first = self.post()
        second = self.post()
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["id"], first.json()["id"])
        self.assertEqual(RequestNull.objects.count(), 1)
        notify.assert_called_once()

    def test_same_text_later_is_a_new_request(self, notify):
        first = RequestNull.objects.get(pk=self.post().json()["id"])
        RequestNull.objects.filter(pk=first.pk).update(created_at=timezone.now() - timedelta(minutes=11))
        self.assertEqual(self.post().status_code, 201)
        self.assertEqual(RequestNull.objects.count(), 2)

    def test_notification_failure_still_creates_request(self, notify):
        notify.side_effect = OSError("smtp down")
        response = self.post()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(RequestNull.objects.count(), 1)

    def test_csrf_not_required(self, notify):
        from django.test import Client as TestClient

        strict = TestClient(enforce_csrf_checks=True)
        response = strict.post(
            reverse(URL_NAME), data=json.dumps(PAYLOAD), content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {TOKEN}",
        )
        self.assertEqual(response.status_code, 201)
