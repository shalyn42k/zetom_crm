# claude — an offer goes to the client only after another person verified it.
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from crm.notification.models import Notification, NotificationKind
from crm.status_manager.services.statuses import Status
from crm.zetom.models import Oferta, RequestAttachment

User = get_user_model()
V = Oferta.Verification


class OfertaVerificationTests(TestCase):
    def setUp(self):
        self.author = User.objects.create_superuser("anna", "anna@zetom.pl", "x", first_name="Anna", last_name="Nowak")
        self.checker = User.objects.create_superuser("piotr", "piotr@zetom.pl", "x", first_name="Piotr", last_name="Kos")
        # staff without any role: can't verify
        self.outsider = User.objects.create_user("jan", "jan@zetom.pl", "x", is_staff=True)
        # field values match _save_offer(), so "save without changes" really changes nothing
        self.oferta = Oferta.objects.create(first_name="Jan", last_name="Kowalski", phone="+48501600300",
                                            email="jan@acme.pl", company_name="Acme", offer_number="LTO/1/2026-11",
                                            subject="wzorcowania", place_of_work="", confirmation_document="",
                                            payment_terms="")
        self.oferta.assigned_to.add(self.author, self.checker)
        self.url = reverse("admin:zetom_oferta_change", args=[self.oferta.pk])
        self.send_url = reverse("admin:zetom_oferta_send_to_client", args=[self.oferta.pk])
        self.request_url = reverse("admin:zetom_oferta_request_verification", args=[self.oferta.pk])
        self.resolve_url = reverse("admin:zetom_oferta_resolve_verification", args=[self.oferta.pk])

    def tearDown(self):
        for a in RequestAttachment.objects.all():
            a.file.delete(save=False)

    def _as(self, user):
        self.client.force_login(user)

    def _send(self):
        return self.client.post(self.send_url, {"to": "jan@acme.pl", "subject": "Oferta", "message": "Dzień dobry"})

    def _request(self, *reviewers, note=""):
        return self.client.post(self.request_url, {"reviewer_ids": [u.pk for u in reviewers], "note": note})

    def _resolve(self, decision, note=""):
        return self.client.post(self.resolve_url, {"decision": decision, "note": note})

    def _notifications(self, kind, user):
        return Notification.objects.filter(
            kind=kind, recipient=user,
            target_content_type=ContentType.objects.get_for_model(Oferta), target_object_id=self.oferta.pk,
        )

    def _save_offer(self, **extra):
        data = {
            "offer_number": "LTO/1/2026-11", "offer_date": "", "subject": "wzorcowania", "inquiry_channel": "email",
            "inquiry_date": "", "extra_costs": "", "vat_rate": "23", "place_of_work": "", "completion_term": "",
            "confirmation_document": "", "payment_terms": "", "notes": "",
            "first_name": "Jan", "last_name": "Kowalski", "company_name": "Acme", "company_nip": "",
            "email": "jan@acme.pl", "phone": "+48501600300",
            "items-TOTAL_FORMS": "0", "items-INITIAL_FORMS": "0", "items-MIN_NUM_FORMS": "0", "items-MAX_NUM_FORMS": "1000",
            "_continue": "1",
        }
        data.update(extra)
        return self.client.post(self.url, data)

    # ---- sending is blocked until verified --------------------------------

    def test_new_offer_is_not_verified_and_cannot_be_sent(self):
        self._as(self.author)
        self.assertEqual(self.oferta.verification_status, V.NONE)
        response = self._send()
        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 0)
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.status, Status.new)

    def test_window_shows_disabled_send_button_and_no_send_dialog(self):
        self._as(self.author)
        html = self.client.get(self.url).content.decode()
        self.assertIn('id="de-send-blocked"', html)
        self.assertIn("disabled", html)
        self.assertNotIn("data-de-send-open", html)
        self.assertNotIn("data-de-send-overlay", html)
        self.assertIn(self.request_url, html)

    def test_pending_offer_cannot_be_sent(self):
        self._as(self.author)
        self._request(self.checker)
        self._send()
        self.assertEqual(len(mail.outbox), 0)

    # ---- the happy path ---------------------------------------------------

    def test_request_approve_then_send(self):
        self._as(self.author)
        response = self._request(self.checker, note="Sprawdź ceny")
        self.assertEqual(response.status_code, 302)
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.verification_status, V.PENDING)
        self.assertEqual(self.oferta.verification_requested_by, self.author)
        self.assertTrue(self._notifications(NotificationKind.REVIEW_REQUEST, self.checker).exists())

        self._as(self.checker)
        html = self.client.get(self.url).content.decode()
        self.assertIn(self.resolve_url, html)
        self._resolve("approved", note="OK")
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.verification_status, V.APPROVED)
        self.assertEqual(self.oferta.verified_by, self.checker)
        self.assertEqual(self.oferta.verification_note, "OK")
        self.assertTrue(self._notifications(NotificationKind.REVIEW_RESOLVED, self.author).exists())
        self.assertFalse(self._notifications(NotificationKind.REVIEW_REQUEST, self.checker).filter(is_read=False).exists())

        self._as(self.author)
        self.assertIn("data-de-send-open", self.client.get(self.url).content.decode())
        self._send()
        self.assertEqual(len(mail.outbox), 1)
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.status, Status.waiting)

    # ---- "another person" -------------------------------------------------

    def test_requester_cannot_verify_own_offer(self):
        self._as(self.author)
        self._request(self.checker)
        self.assertNotIn(self.resolve_url, self.client.get(self.url).content.decode())
        response = self._resolve("approved")
        self.assertEqual(response.status_code, 403)
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.verification_status, V.PENDING)

    def test_requester_is_not_offered_as_reviewer(self):
        self._as(self.author)
        candidates = self.client.get(self.url).context["doc_window"]["verification"]["candidates"]
        self.assertIn(self.checker, candidates)
        self.assertNotIn(self.author, candidates)
        self.assertNotIn(self.outsider, candidates)

    def test_request_needs_an_eligible_reviewer(self):
        self._as(self.author)
        self._request(self.outsider)
        self._request(self.author)
        self._request()
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.verification_status, V.NONE)
        self.assertFalse(Notification.objects.exists())

    def test_user_without_review_rights_cannot_resolve(self):
        self._as(self.author)
        self._request(self.checker)
        self.oferta.assigned_to.add(self.outsider)
        self._as(self.outsider)
        self._resolve("approved")
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.verification_status, V.PENDING)

    # ---- reject / re-request ----------------------------------------------

    def test_reject_then_request_again(self):
        self._as(self.author)
        self._request(self.checker)
        self._as(self.checker)
        self._resolve("rejected", note="Zła cena")
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.verification_status, V.REJECTED)
        self._as(self.author)
        self._send()
        self.assertEqual(len(mail.outbox), 0)
        self._request(self.checker)
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.verification_status, V.PENDING)
        self.assertEqual(self.oferta.verified_by, None)

    def test_cannot_request_twice_while_pending(self):
        self._as(self.author)
        self._request(self.checker)
        self._request(self.checker)
        self.assertEqual(self._notifications(NotificationKind.REVIEW_REQUEST, self.checker).count(), 1)

    # ---- edits after approval ---------------------------------------------

    def _approve(self):
        self._as(self.author)
        self._request(self.checker)
        self._as(self.checker)
        self._resolve("approved")
        self._as(self.author)

    def test_editing_after_approval_needs_new_verification(self):
        self._approve()
        response = self._save_offer(completion_term="grudzień 2026 r.")
        self.assertEqual(response.status_code, 302)
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.completion_term, "grudzień 2026 r.")
        self.assertEqual(self.oferta.verification_status, V.NONE)
        # the first save moves new -> in_progress, which mails the client a
        # short "in progress" notice (no document) — not what we check here
        mail.outbox.clear()
        self._send()
        self.assertEqual(len(mail.outbox), 0)

    def test_adding_an_item_after_approval_needs_new_verification(self):
        self._approve()
        self._save_offer(**{
            "items-TOTAL_FORMS": "1", "items-0-name": "Suwmiarka", "items-0-details": "", "items-0-norm": "",
            "items-0-quantity": "1", "items-0-unit_price": "100",
        })
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.items.count(), 1)
        self.assertEqual(self.oferta.verification_status, V.NONE)

    def test_saving_without_changes_keeps_approval(self):
        self._approve()
        self._save_offer()
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.verification_status, V.APPROVED)

    def test_editing_while_pending_cancels_the_request(self):
        self._as(self.author)
        self._request(self.checker)
        self._save_offer(completion_term="styczeń 2027 r.")
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.verification_status, V.NONE)
        self.assertFalse(self._notifications(NotificationKind.REVIEW_REQUEST, self.checker).filter(is_read=False).exists())

    # ---- other documents are not affected ---------------------------------

    def test_zlecenie_window_has_no_verification(self):
        from crm.zetom.models import Zlecenie

        zlecenie = Zlecenie.objects.create(first_name="Jan", email="jan@acme.pl", phone="+48501600300")
        zlecenie.assigned_to.add(self.author)
        self._as(self.author)
        response = self.client.get(reverse("admin:zetom_zlecenie_change", args=[zlecenie.pk]))
        self.assertNotIn("verification", response.context["doc_window"])
        self.assertIsNone(response.context["doc_window"]["send_blocked"])
