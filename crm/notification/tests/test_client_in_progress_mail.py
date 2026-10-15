# ──────────────────────────────────────────────────────────────────────────────
# ТЕСТЫ client_in_progress.txt (crm/notification/services/request_mail.py
# ::send_document_to_client) — письмо клиенту при переходе документа в
# "in_progress".
#
# Found live: a real admin save (Polish locale active, matching every real
# staff member's session) produced "Twoje offer jest teraz w realizacji" —
# the surrounding sentence translated, but document_kind itself was a bare
# raw English noun ("offer"/"order"/"application") substituted straight
# into the template, with the possessive pronoun ("Twoje") not even
# matching that noun's grammatical gender in Polish. Fixed by branching the
# template into three fully independent, correctly-declined sentences
# (oferta=feminine, zlecenie=neuter, wniosek=masculine) instead of
# substituting a single noun variable.
# ──────────────────────────────────────────────────────────────────────────────

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import translation

from crm.notification.services.request_mail import send_document_to_client
from crm.status_manager.services.statuses import Status
from crm.zetom.models import Oferta, RequestMain, Wniosek, Zlecenie

BASE = {"phone": "+48501600300", "email": "jan@zetom.pl"}


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@test.com",
)
class ClientInProgressGenderAgreementTests(TestCase):
    def setUp(self):
        self.main = RequestMain.objects.create(**BASE, company_name="Zetom")

    def _send_and_get_message(self, document):
        with translation.override("pl"):
            send_document_to_client(document)
        return mail.outbox[-1]

    def test_oferta_uses_feminine_agreement(self):
        oferta = Oferta.objects.create(**BASE, from_main=self.main, status=Status.in_progress)
        message = self._send_and_get_message(oferta)
        self.assertIn("Twoja oferta", message.subject)
        self.assertNotIn("offer", message.subject.lower())
        self.assertIn("została zaakceptowana", message.body)

    def test_zlecenie_uses_neuter_agreement(self):
        zlecenie = Zlecenie.objects.create(**BASE, from_main=self.main, status=Status.in_progress)
        message = self._send_and_get_message(zlecenie)
        self.assertIn("Twoje zlecenie", message.subject)
        self.assertNotIn("order", message.subject.lower())
        self.assertIn("zostało zaakceptowane", message.body)

    def test_wniosek_uses_masculine_agreement(self):
        wniosek = Wniosek.objects.create(**BASE, from_main=self.main, status=Status.in_progress)
        message = self._send_and_get_message(wniosek)
        self.assertIn("Twój wniosek", message.subject)
        self.assertNotIn("application", message.subject.lower())
        self.assertIn("został zaakceptowany", message.body)

    def test_renders_in_english_by_default(self):
        oferta = Oferta.objects.create(**BASE, from_main=self.main, status=Status.in_progress)
        send_document_to_client(oferta)
        message = mail.outbox[-1]
        self.assertIn("your offer is now in progress", message.subject)
