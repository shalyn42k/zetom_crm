from django.http import Http404
from django.test import TestCase

from crm.zetom.models import Oferta, RequestMain, RequestNull, Wniosek, Zlecenie
from crm.zetom.services.request_service import (
    approve_null_action,
    approve_oferta_action,
    approve_wniosek_action,
    approve_zlecenie_action,
)
from crm.zetom.services.statuses import Status


BASE_DATA = {
    "phone": "+48501600300",
    "company_name": "Zetom Sp. z o.o.",
    "email": "contact@zetom.pl",
    "company_nip": "7322215365",
}


class ApproveNullActionTests(TestCase):
    def test_creates_main_from_null_and_soft_deletes_null(self):
        null = RequestNull.objects.create(**BASE_DATA, message="hello")

        main = approve_null_action(null.pk)

        self.assertIsInstance(main, RequestMain)
        self.assertEqual(main.company_name, null.company_name)
        self.assertEqual(main.email, null.email)
        self.assertEqual(main.company_nip, null.company_nip)
        self.assertEqual(main.message, "hello")
        self.assertFalse(
            RequestNull.objects.filter(pk=null.pk).exists(),
            "safedelete should hide the null row from default manager",
        )

    def test_raises_404_when_null_missing(self):
        with self.assertRaises(Http404):
            approve_null_action(999999)


class ApproveChildActionTests(TestCase):
    def setUp(self):
        self.main = RequestMain.objects.create(**BASE_DATA)

    def test_approve_oferta_creates_child_and_updates_parent(self):
        oferta = approve_oferta_action(self.main.pk)
        self.main.refresh_from_db()
        self.assertIsInstance(oferta, Oferta)
        self.assertEqual(oferta.from_main, self.main)
        self.assertEqual(oferta.price, 0)
        self.assertEqual(oferta.status, Status.new)
        self.assertFalse(self.main.is_archived)

    def test_approve_zlecenie_creates_child(self):
        zlec = approve_zlecenie_action(self.main.pk)
        self.assertIsInstance(zlec, Zlecenie)
        self.assertEqual(zlec.from_main, self.main)
        self.assertEqual(zlec.price, 0)

    def test_approve_wniosek_creates_child(self):
        wn = approve_wniosek_action(self.main.pk)
        self.assertIsInstance(wn, Wniosek)
        self.assertEqual(wn.from_main, self.main)

    def test_raises_404_for_missing_main(self):
        for fn in (
            approve_oferta_action,
            approve_zlecenie_action,
            approve_wniosek_action,
        ):
            with self.assertRaises(Http404):
                fn(999999)
