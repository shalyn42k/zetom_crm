# claude
"""Whole-site smoke test: every admin page (changelist / add / change) and
every custom page, opened by each role, in Polish. Fails on any server
error (an exception or a 5xx); 403/404/redirect are fine — they are
permission answers, not crashes.

With SMOKE_DUMP=<dir> set, also writes the visible text of every page
there, for reviewing untranslated leftovers by eye.
"""
import os
import re
from html import unescape

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from crm.clients.models import Client, Company
from crm.status_manager.services.statuses import RequestStatus
from crm.users.models import Role
from crm.zetom.models import (
    Oferta, RequestMain, RequestNull, StepNote, Wniosek, Zlecenie,
)

User = get_user_model()

BASE = {
    "first_name": "Jan", "last_name": "Kowalski", "phone": "+48501600300",
    "email": "jan@client.pl", "company_name": "Acme", "departments": ["sales"],
}

_SIMPLE_STATIC = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

ROLES = ("admin", "department_head", "specialist", "auditor")


def _visible_text(html):
    html = re.sub(r"(?is)<(script|style|svg|template)\b.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", "\n", html)
    lines = [re.sub(r"\s+", " ", unescape(line)).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


@override_settings(STORAGES=_SIMPLE_STATIC)
class SiteSmokeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users = {}
        for code in ROLES:
            u = User.objects.create_user(
                username=f"smoke_{code}", password="x", is_staff=True,
                email=f"{code}@zetom.pl", first_name="Smoke", last_name=code,
            )
            u.profile.role = Role.objects.get(code=code)
            u.profile.departments = ["sales"]
            if code == "department_head":
                u.profile.head_of_departments = ["sales"]
            u.profile.save()
            cls.users[code] = u
        cls.users["superuser"] = User.objects.create_superuser("smoke_root", "root@zetom.pl", "x")
        everyone = list(cls.users.values())

        cls.null = RequestNull.objects.create(**BASE)
        cls.main = RequestMain.objects.create(**BASE)
        cls.oferta = Oferta.objects.create(from_main=cls.main, price="100", notes="n", **BASE)
        cls.zlecenie = Zlecenie.objects.create(from_main=cls.main, from_oferta=cls.oferta, **BASE)
        cls.wniosek = Wniosek.objects.create(from_main=cls.main, from_zlecenie=cls.zlecenie, **BASE)
        cls.cancelled = RequestMain.objects.create(status=RequestStatus.cancelled, **BASE)
        cls.deleted = RequestMain.objects.create(**BASE)
        cls.deleted.delete()  # soft delete
        cls.cancelled_null = RequestNull.objects.create(status=RequestStatus.cancelled, **BASE)
        for obj in (cls.null, cls.main, cls.oferta, cls.zlecenie, cls.wniosek, cls.cancelled, cls.cancelled_null):
            obj.assigned_to.add(*everyone)

        cls.person = Client.objects.create(first_name="Anna", last_name="Nowak", email="anna@client.pl")
        cls.company = Company.objects.create(name="Acme Sp. z o.o.", nip="1234563218")
        StepNote.objects.create(
            author=cls.users["specialist"], target=cls.main, kind=StepNote.Kind.REMINDER,
            text="call", next_contact_at=timezone.now() + timezone.timedelta(days=1),
        )

    def _urls(self):
        urls = [reverse("admin:index")]
        for model, model_admin in admin.site._registry.items():
            opts = model._meta
            prefix = f"admin:{opts.app_label}_{opts.model_name}"
            urls.append(reverse(f"{prefix}_changelist"))
            urls.append(reverse(f"{prefix}_add"))
            obj = model_admin.get_queryset(self._request_for(self.users["superuser"])).first()
            if obj is not None:
                urls.append(reverse(f"{prefix}_change", args=[obj.pk]))
                urls.append(reverse(f"{prefix}_history", args=[obj.pk]))
        extra = [
            ("admin:zetom_requestnull_validate", [self.null.pk]),
            ("admin:zetom_oferta_print", [self.oferta.pk]),
            ("admin:zetom_zlecenie_print", [self.zlecenie.pk]),
            ("admin:zetom_wniosek_print", [self.wniosek.pk]),
            ("admin:zetom_oferta_delete", [self.oferta.pk]),
            ("admin:zetom_requestmain_delete", [self.main.pk]),
            ("notification:inbox", []),
            ("notification:settings", []),
            ("notification:unread_count", []),
            ("user_profile_edit", []),
            ("user_list", []),
            ("user_detail", [self.users["specialist"].pk]),
            ("user_edit", [self.users["specialist"].pk]),
            ("user_create", []),
            ("zetom:index", []),
        ]
        for name, args in extra:
            try:
                urls.append(reverse(name, args=args))
            except NoReverseMatch:
                pass
        urls.append(reverse("admin:auth_user_change", args=[self.users["specialist"].pk]) + "?tab=notifications")
        urls.append(reverse("admin:auth_user_change", args=[self.users["specialist"].pk]) + "?tab=permissions")
        urls.append(reverse("admin:auth_user_change", args=[self.users["specialist"].pk]) + "?tab=departments")
        urls.append(reverse("clients:search") + "?q=Now")
        return urls

    def _request_for(self, user):
        from django.test import RequestFactory

        request = RequestFactory().get("/")
        request.user = user
        return request

    def test_no_page_crashes_for_any_role(self):
        dump = os.environ.get("SMOKE_DUMP")
        failures = []
        urls = self._urls()
        for role, user in self.users.items():
            self.client.force_login(user)
            self.client.cookies["django_language"] = "pl"
            for url in urls:
                try:
                    response = self.client.get(url, HTTP_ACCEPT_LANGUAGE="pl")
                except Exception as exc:  # noqa: BLE001 — collect every crash, report all at once
                    failures.append(f"{role} {url}: {type(exc).__name__}: {exc}")
                    continue
                if response.status_code >= 500:
                    failures.append(f"{role} {url}: HTTP {response.status_code}")
                elif dump and response.status_code == 200 and "html" in response.get("Content-Type", ""):
                    os.makedirs(dump, exist_ok=True)
                    name = re.sub(r"[^\w]+", "_", url).strip("_") or "root"
                    with open(os.path.join(dump, f"{role}__{name}.txt"), "w") as fh:
                        fh.write(_visible_text(response.content.decode()))
        self.assertEqual(failures, [], "\n".join(failures))
