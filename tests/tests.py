from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import resolve

from zetom.forms import AddRecordForm, SignUpForm
from zetom.models import Record


@override_settings(
    DATABASES={
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }
)
class RecordModelTests(TestCase):
    def test_record_creation_and_string_representation(self):
        record = Record.objects.create(
            first_name="Ivan",
            last_name="Petrov",
            email="ivan@example.com",
            phone="123456789",
            address="Main st 1",
            city="Warsaw",
            state="Mazovia",
            zipcode="00-001",
        )

        self.assertIsNotNone(record.pk)
        self.assertEqual(str(record), "Ivan Petrov")


@override_settings(
    DATABASES={
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }
)
class FormsTests(TestCase):
    def test_signup_form_creates_user(self):
        form = SignUpForm(
            data={
                "username": "iso_user",
                "first_name": "Iso",
                "last_name": "Tester",
                "email": "iso@example.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertTrue(User.objects.filter(username="iso_user").exists())
        self.assertEqual(user.email, "iso@example.com")

    def test_add_record_form_valid_data(self):
        form = AddRecordForm(
            data={
                "first_name": "John",
                "last_name": "Doe",
                "email": "john@example.com",
                "phone": "123123123",
                "address": "Street 2",
                "city": "Krakow",
                "state": "Malopolska",
                "zipcode": "30-001",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        instance = form.save()
        self.assertEqual(instance.first_name, "John")


class UrlsAndModulesSmokeTests(SimpleTestCase):
    def test_admin_url_is_resolvable(self):
        match = resolve("/admin/")
        self.assertEqual(match.url_name, "index")

    def test_zetom_urls_module_has_urlpatterns(self):
        from zetom import urls

        self.assertTrue(hasattr(urls, "urlpatterns"))
        self.assertIsInstance(urls.urlpatterns, list)

    def test_views_module_imports(self):
        from zetom import views

        self.assertTrue(hasattr(views, "render"))
