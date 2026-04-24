from decimal import Decimal

from django.test import TestCase

from crm.zetom.forms import (
    AddOferta,
    AddRequestFormMain,
    AddRequestFormNull,
    AddWniosek,
    AddZlecenie,
)
from crm.zetom.models import RequestMain


BASE_DATA = {
    "phone": "+48501600300",
    "company_name": "Zetom Sp. z o.o.",
    "email": "contact@zetom.pl",
    "company_nip": "7322215365",
}


class AddRequestFormNullTests(TestCase):
    def test_valid_with_polish_nip_and_phone(self):
        form = AddRequestFormNull(data=BASE_DATA)
        self.assertTrue(form.is_valid(), form.errors)

    def test_message_is_optional(self):
        form = AddRequestFormNull(data=BASE_DATA)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data.get("message", ""), "")

    def test_company_name_is_optional(self):
        data = {**BASE_DATA, "company_name": ""}
        form = AddRequestFormNull(data=data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_invalid_nip_fails_validation(self):
        form = AddRequestFormNull(data={**BASE_DATA, "company_nip": "not-a-nip"})
        self.assertFalse(form.is_valid())
        self.assertIn("company_nip", form.errors)

    def test_invalid_email_fails_validation(self):
        form = AddRequestFormNull(data={**BASE_DATA, "email": "not-email"})
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_invalid_phone_fails_validation(self):
        form = AddRequestFormNull(data={**BASE_DATA, "phone": "123"})
        self.assertFalse(form.is_valid())
        self.assertIn("phone", form.errors)

    def test_missing_required_email_fails(self):
        data = {**BASE_DATA}
        data.pop("email")
        form = AddRequestFormNull(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)


class AddRequestFormMainTests(TestCase):
    def test_valid_with_optional_full_name_and_address(self):
        form = AddRequestFormMain(
            data={
                **BASE_DATA,
                "full_name": "John Johnson",
                "address": "ulica Hallera 76/49",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_full_name_and_address_are_optional(self):
        form = AddRequestFormMain(data=BASE_DATA)
        self.assertTrue(form.is_valid(), form.errors)


class AddChildFormsTests(TestCase):
    def setUp(self):
        self.main = RequestMain.objects.create(**BASE_DATA)

    def test_add_oferta_valid(self):
        form = AddOferta(
            data={**BASE_DATA, "from_main": self.main.pk, "price": "12.50"}
        )
        self.assertTrue(form.is_valid(), form.errors)
        obj = form.save()
        self.assertEqual(obj.price, Decimal("12.50"))
        self.assertEqual(obj.from_main, self.main)

    def test_add_zlecenie_valid_without_price(self):
        form = AddZlecenie(data={**BASE_DATA, "from_main": self.main.pk})
        self.assertTrue(form.is_valid(), form.errors)

    def test_add_wniosek_valid(self):
        form = AddWniosek(data={**BASE_DATA, "from_main": self.main.pk})
        self.assertTrue(form.is_valid(), form.errors)

    def test_form_control_class_applied_via_template_init(self):
        form = AddOferta()
        for field in form.fields.values():
            self.assertIn("form-control", field.widget.attrs.get("class", ""))
