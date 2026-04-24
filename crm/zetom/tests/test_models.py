from django.core.exceptions import ValidationError
from django.test import TestCase

from crm.zetom.models import (
    DepartmentsVariants,
    Oferta,
    RequestMain,
    RequestNull,
    Wniosek,
    Zlecenie,
)
from crm.zetom.services.statuses import Status


VALID_NULL_DATA = {
    "phone": "+48501600300",
    "company_name": "Zetom Sp. z o.o.",
    "email": "contact@zetom.pl",
    "company_nip": "7322215365",
}


class RequestNullModelTests(TestCase):
    def test_create_request_null_persists_fields(self):
        obj = RequestNull.objects.create(**VALID_NULL_DATA, message="hi")

        obj.refresh_from_db()
        self.assertEqual(obj.company_name, "Zetom Sp. z o.o.")
        self.assertEqual(obj.email, "contact@zetom.pl")
        self.assertEqual(obj.company_nip, "7322215365")
        self.assertEqual(obj.message, "hi")
        self.assertEqual(obj.department, DepartmentsVariants.DEPARTMENT_0)

    def test_str_returns_company_name(self):
        obj = RequestNull.objects.create(**VALID_NULL_DATA)
        self.assertEqual(str(obj), "Zetom Sp. z o.o.")

    def test_nip_regex_rejects_non_digit(self):
        obj = RequestNull(**{**VALID_NULL_DATA, "company_nip": "abc1234567"})
        with self.assertRaises(ValidationError):
            obj.full_clean()

    def test_nip_regex_rejects_wrong_length(self):
        obj = RequestNull(**{**VALID_NULL_DATA, "company_nip": "123"})
        with self.assertRaises(ValidationError):
            obj.full_clean()


class RequestMainModelTests(TestCase):
    def test_defaults_are_new_and_not_archived(self):
        main = RequestMain.objects.create(**VALID_NULL_DATA)
        self.assertEqual(main.status, Status.new)
        self.assertFalse(main.is_archived)

    def test_from_null_can_be_set(self):
        null = RequestNull.objects.create(**VALID_NULL_DATA)
        main = RequestMain.objects.create(**VALID_NULL_DATA, from_null=null)
        self.assertEqual(main.from_null, null)

    def test_from_null_is_set_null_on_parent_delete(self):
        null = RequestNull.objects.create(**VALID_NULL_DATA)
        main = RequestMain.objects.create(**VALID_NULL_DATA, from_null=null)
        null.delete(force_policy=0)
        main.refresh_from_db()
        self.assertIsNone(main.from_null)


class ChildModelsTests(TestCase):
    def setUp(self):
        self.main = RequestMain.objects.create(**VALID_NULL_DATA)

    def test_oferta_links_to_main(self):
        oferta = Oferta.objects.create(**VALID_NULL_DATA, from_main=self.main, price=10)
        self.assertEqual(oferta.from_main, self.main)
        self.assertEqual(oferta.status, Status.new)
        self.assertIn(oferta, self.main.oferta_set.all())

    def test_zlecenie_links_to_main(self):
        zlec = Zlecenie.objects.create(**VALID_NULL_DATA, from_main=self.main, price=20)
        self.assertEqual(zlec.from_main, self.main)
        self.assertIn(zlec, self.main.zlecenie_set.all())

    def test_wniosek_links_to_main(self):
        wn = Wniosek.objects.create(**VALID_NULL_DATA, from_main=self.main)
        self.assertEqual(wn.from_main, self.main)
        self.assertIn(wn, self.main.wniosek_set.all())

    def test_children_soft_cascade_when_main_deleted(self):
        """Default delete() on RequestMain should soft-cascade its children
        via SOFT_DELETE_CASCADE policy — they disappear from default manager
        but stay in the database under all_with_deleted()."""
        Oferta.objects.create(**VALID_NULL_DATA, from_main=self.main)
        Zlecenie.objects.create(**VALID_NULL_DATA, from_main=self.main)
        Wniosek.objects.create(**VALID_NULL_DATA, from_main=self.main)

        self.main.delete()

        self.assertEqual(Oferta.objects.count(), 0)
        self.assertEqual(Zlecenie.objects.count(), 0)
        self.assertEqual(Wniosek.objects.count(), 0)
        self.assertEqual(Oferta.objects.all_with_deleted().count(), 1)
        self.assertEqual(Zlecenie.objects.all_with_deleted().count(), 1)
        self.assertEqual(Wniosek.objects.all_with_deleted().count(), 1)

    def test_children_hard_cascade_when_main_hard_deleted(self):
        """Sanity check that the DB-level CASCADE constraint is still in
        place: forcing HARD_DELETE physically removes children too."""
        Oferta.objects.create(**VALID_NULL_DATA, from_main=self.main)
        Zlecenie.objects.create(**VALID_NULL_DATA, from_main=self.main)
        Wniosek.objects.create(**VALID_NULL_DATA, from_main=self.main)

        self.main.delete(force_policy=0)

        self.assertEqual(Oferta.objects.all_with_deleted().count(), 0)
        self.assertEqual(Zlecenie.objects.all_with_deleted().count(), 0)
        self.assertEqual(Wniosek.objects.all_with_deleted().count(), 0)
