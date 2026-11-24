# claude — the card endpoints assign raw POST strings to the model and never
# run a ModelForm, so PhoneNumberField happily stored garbage: "not-a-phone"
# came back out as the string "None", and "12345" was saved as "+48 12345".
# Email was already guarded; phone now is too.
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from crm.clients.models import Client, Company, CompanyPersonLink

BAD_PHONES = ["not-a-phone", "12345"]


class PhoneValidationTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("staff", "s@s.pl", "pass12345")
        self.client.force_login(self.user)
        self.person = Client.objects.create(first_name="Jan", last_name="Kowalski")
        self.company = Company.objects.create(name="Zetom")
        self.link = CompanyPersonLink.objects.create(
            company=self.company, person=self.person,
        )

    def test_person_save_rejects_bad_phone(self):
        url = reverse("admin:clients_client_person_save", args=[self.person.pk])
        for phone in BAD_PHONES:
            with self.subTest(phone=phone):
                resp = self.client.post(
                    url, {"first_name": "Jan", "last_name": "K", "email": "", "phone": phone},
                    HTTP_HOST="127.0.0.1",
                )
                self.assertEqual(resp.status_code, 400)
                self.assertFalse(resp.json()["ok"])
                self.person.refresh_from_db()
                self.assertFalse(self.person.phone)

    def test_person_save_accepts_valid_phone(self):
        url = reverse("admin:clients_client_person_save", args=[self.person.pk])
        resp = self.client.post(
            url, {"first_name": "Jan", "last_name": "K", "email": "", "phone": "+48501600300"},
            HTTP_HOST="127.0.0.1",
        )
        self.assertTrue(resp.json()["ok"])
        self.person.refresh_from_db()
        self.assertEqual(self.person.phone.as_e164, "+48501600300")

    def test_company_person_add_rejects_bad_phone(self):
        url = reverse("admin:clients_company_person_add", args=[self.company.pk])
        resp = self.client.post(
            url, {"first_name": "A", "last_name": "B", "email": "", "phone": "12345"},
            HTTP_HOST="127.0.0.1",
        )
        self.assertEqual(resp.status_code, 400)
        # no half-created person left behind (the create is inside the guard)
        self.assertFalse(Client.objects.filter(first_name="A", last_name="B").exists())

    def test_company_person_edit_rejects_bad_phone(self):
        url = reverse(
            "admin:clients_company_person_edit", args=[self.company.pk, self.link.pk],
        )
        resp = self.client.post(
            url, {"first_name": "Jan", "last_name": "K", "email": "", "phone": "not-a-phone"},
            HTTP_HOST="127.0.0.1",
        )
        self.assertEqual(resp.status_code, 400)
        self.person.refresh_from_db()
        self.assertFalse(self.person.phone)

    def test_empty_phone_still_allowed(self):
        url = reverse("admin:clients_client_person_save", args=[self.person.pk])
        resp = self.client.post(
            url, {"first_name": "Jan", "last_name": "K", "email": "", "phone": ""},
            HTTP_HOST="127.0.0.1",
        )
        self.assertTrue(resp.json()["ok"])
        self.person.refresh_from_db()
        self.assertIsNone(self.person.phone)

    def test_email_still_validated(self):
        url = reverse("admin:clients_client_person_save", args=[self.person.pk])
        resp = self.client.post(
            url, {"first_name": "Jan", "last_name": "K", "email": "nope", "phone": ""},
            HTTP_HOST="127.0.0.1",
        )
        self.assertEqual(resp.status_code, 400)
