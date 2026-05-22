# ──────────────────────────────────────────────────────────────────────────────
# ТЕСТЫ ФОРМ
#
# Что тут тестируется:
#   • Валидные данные проходят form.is_valid()
#   • Невалидные данные дают нужные ключи в form.errors
#   • Опциональные поля действительно не обязательны
#   • form.save() создаёт объект с правильными значениями
#
# Зачем тестировать формы отдельно от вьюшек:
#   Форма — отдельный слой логики (валидация, виджеты, кастомные поля).
#   Тест формы быстрее и точнее показывает, ЧТО именно сломалось.
#
# Важные изменения в формах:
#   • AddRequestFormNull: company_nip убран, first_name/last_name обязательны
#   • AddRequestFormMain: добавлен source (обязательное поле)
#   • AddOferta/Zlecenie/Wniosek: требуют source
# ──────────────────────────────────────────────────────────────────────────────

from decimal import Decimal

from django.test import TestCase

from crm.zetom.forms import (
    AddOferta,
    AddRequestFormMain,
    AddRequestFormNull,
    AddWniosek,
    AddZlecenie,
)
from crm.zetom.models import RequestMain, RequestSource


# ─────────────────────────── AddRequestFormNull ───────────────────────────────

class AddRequestFormNullTests(TestCase):
    """Форма публичной заявки (лендинг/сайт).

    Обязательные поля: first_name, last_name, phone, email.
    company_nip — убран в __init__ (не нужен на первичном обращении).
    """

    # Минимальный набор для успешной валидации
    VALID = {
        "first_name": "Jan",
        "last_name": "Kowalski",
        "phone": "+48501600300",
        "email": "contact@zetom.pl",
    }

    def test_valid_minimal_data_passes(self):
        form = AddRequestFormNull(data=self.VALID)
        # form.errors выведет понятное сообщение если тест упадёт
        self.assertTrue(form.is_valid(), form.errors)

    def test_optional_message_is_accepted(self):
        form = AddRequestFormNull(data={**self.VALID, "message": "Interesting note"})
        self.assertTrue(form.is_valid(), form.errors)

    def test_optional_company_name_is_accepted(self):
        form = AddRequestFormNull(data={**self.VALID, "company_name": "Zetom"})
        self.assertTrue(form.is_valid(), form.errors)

    def test_missing_first_name_fails(self):
        # AddRequestFormNull.__init__ устанавливает first_name.required = True
        data = {k: v for k, v in self.VALID.items() if k != "first_name"}
        form = AddRequestFormNull(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("first_name", form.errors)

    def test_missing_last_name_fails(self):
        data = {k: v for k, v in self.VALID.items() if k != "last_name"}
        form = AddRequestFormNull(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("last_name", form.errors)

    def test_missing_email_fails(self):
        data = {k: v for k, v in self.VALID.items() if k != "email"}
        form = AddRequestFormNull(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_invalid_email_fails(self):
        form = AddRequestFormNull(data={**self.VALID, "email": "not-an-email"})
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_invalid_phone_fails(self):
        form = AddRequestFormNull(data={**self.VALID, "phone": "abc"})
        self.assertFalse(form.is_valid())
        self.assertIn("phone", form.errors)

    def test_company_nip_field_is_removed(self):
        # __init__ делает self.fields.pop("company_nip") — поля нет в форме.
        # Передавать company_nip в POST бессмысленно — оно игнорируется.
        form = AddRequestFormNull()
        self.assertNotIn("company_nip", form.fields)

    def test_form_control_class_on_all_widgets(self):
        # TemplateForm.__init__ добавляет class="form-control" ко всем виджетам.
        # Без этого Bootstrap стили не применятся.
        form = AddRequestFormNull()
        for name, field in form.fields.items():
            if name == "client":
                continue  # ClientField имеет собственный класс
            self.assertIn(
                "form-control",
                field.widget.attrs.get("class", ""),
                msg=f"field '{name}' missing form-control class",
            )


# ─────────────────────────── AddRequestFormMain ───────────────────────────────

class AddRequestFormMainTests(TestCase):
    """Форма полной заявки (создаётся в Django admin).

    Обязательные: phone, email, company_nip, source.
    Опциональные: first_name, last_name, address, message, company_name.
    """

    VALID = {
        "first_name": "Jan",
        "last_name": "Kowalski",
        "phone": "+48501600300",
        "email": "contact@zetom.pl",
        "company_nip": "7322215365",
        "source": RequestSource.PHONE,
    }

    def test_valid_data_passes(self):
        form = AddRequestFormMain(data=self.VALID)
        self.assertTrue(form.is_valid(), form.errors)

    def test_optional_address_and_message_accepted(self):
        data = {**self.VALID, "address": "ulica Hallera 76/49", "message": "note"}
        form = AddRequestFormMain(data=data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_first_last_name_are_optional(self):
        data = {k: v for k, v in self.VALID.items() if k not in ("first_name", "last_name")}
        form = AddRequestFormMain(data=data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_invalid_nip_fails(self):
        form = AddRequestFormMain(data={**self.VALID, "company_nip": "not-a-nip"})
        self.assertFalse(form.is_valid())
        self.assertIn("company_nip", form.errors)

    def test_missing_source_fails(self):
        # source — blank=False на модели → обязательное поле в форме.
        data = {k: v for k, v in self.VALID.items() if k != "source"}
        form = AddRequestFormMain(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("source", form.errors)

    def test_invalid_email_fails(self):
        form = AddRequestFormMain(data={**self.VALID, "email": "bad"})
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)


# ─────────────────────────── AddOferta / AddZlecenie / AddWniosek ─────────────

class AddChildFormsTests(TestCase):
    """Формы дочерних документов. Все требуют source (blank=False на модели)."""

    def setUp(self):
        self.main = RequestMain.objects.create(
            phone="+48501600300", email="contact@zetom.pl"
        )

    def _base(self):
        return {
            "phone": "+48501600300",
            "email": "contact@zetom.pl",
            "company_nip": "7322215365",
            "source": RequestSource.MANUAL,
            "from_main": self.main.pk,
        }

    def test_add_oferta_valid(self):
        form = AddOferta(data={**self._base(), "price": "12.50"})
        self.assertTrue(form.is_valid(), form.errors)
        obj = form.save()
        self.assertEqual(obj.price, Decimal("12.50"))
        self.assertEqual(obj.from_main, self.main)

    def test_add_oferta_price_is_optional(self):
        # price: DecimalField(required=False) в форме
        form = AddOferta(data=self._base())
        self.assertTrue(form.is_valid(), form.errors)

    def test_add_zlecenie_valid(self):
        form = AddZlecenie(data=self._base())
        self.assertTrue(form.is_valid(), form.errors)

    def test_add_wniosek_valid(self):
        form = AddWniosek(data=self._base())
        self.assertTrue(form.is_valid(), form.errors)

    def test_missing_source_fails_for_all_child_forms(self):
        # subTest: запускает все три проверки независимо — если одна упала,
        # остальные всё равно выполняются, и мы видим все ошибки сразу.
        data = {k: v for k, v in self._base().items() if k != "source"}
        for FormClass in (AddOferta, AddZlecenie, AddWniosek):
            with self.subTest(form=FormClass.__name__):
                form = FormClass(data=data)
                self.assertFalse(form.is_valid())
                self.assertIn("source", form.errors)

    def test_missing_email_fails_for_all_child_forms(self):
        data = {k: v for k, v in self._base().items() if k != "email"}
        for FormClass in (AddOferta, AddZlecenie, AddWniosek):
            with self.subTest(form=FormClass.__name__):
                form = FormClass(data=data)
                self.assertFalse(form.is_valid())
                self.assertIn("email", form.errors)
