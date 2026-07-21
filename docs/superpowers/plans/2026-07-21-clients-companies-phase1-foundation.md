# Clients/Companies — Phase 1 (foundation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ввести нормализованные модели `Company` + `CompanyPersonLink` и FK `RequestMain.company`, забэкфиллить их из существующих `Client.company_*` — additively, ничего не ломая.

**Architecture:** Фаза 1 — чисто additive. `Client` НЕ трогаем (rename и удаление company-полей — Фаза 2). Новые модели живут в `crm/clients/models.py` рядом с `Client`. `CompanyPersonLink.person` пока указывает на `clients.Client`. Data-migration бэкфиллит `Company` из непустых `Client.company_name`/`company_nip`, создаёт связи и проставляет `RequestMain.company`. Логика бэкфилла вынесена в функцию, принимающую классы моделей аргументами — один код и для миграции (`apps.get_model`), и для теста (реальные модели).

**Tech Stack:** Django 5.2, PostgreSQL, `phonenumber_field`, `django.contrib.auth.User`, тесты через `manage.py test` (Django TestCase, не pytest).

## Global Constraints

- Django 5.2 / Postgres. Тесты: `python manage.py test <path>` (не pytest).
- i18n: весь новый user-facing текст — `gettext_lazy as _` в py. Перед завершением фазы: `makemessages -l pl -l en` → перевод PL+EN → `compilemessages` (часть DoD).
- Python-блоки, написанные Claude, помечать комментом `# claude` над блоком.
- Коммиты частые, по задаче. НЕ добавлять `Co-Authored-By: Claude`, если код фактически писал пользователь.
- NIP нормализуется через существующие `crm.clients.validators.normalize_nip` / `validate_nip` (10 цифр, mod-11 контрольная сумма).
- Следующие номера миграций на старте: `clients` = `0006`, `zetom` = `0013`.

---

### Task 1: Модели `Company`, `SupplierType`, `CompanyPersonLink`

**Files:**
- Modify: `crm/clients/models.py` (append после `ClientInteraction`)
- Test: `crm/clients/tests/test_company.py` (создать; каталог `tests/` как в zetom — но у clients сейчас `tests.py`, см. шаг 0)

**Interfaces:**
- Produces:
  - `SupplierType(TextChoices)` со значениями `LOCAL="lokalny"`, `REGIONAL="regionalny"`, `INTERNATIONAL="miedzynarodowy"`.
  - `Company` — поля: `name, short_name, full_name, nip, regon, type_supplier, city, country, street, voivodeship, post_code, phone, email, comments, created_at`; `clean()` нормализует `nip`; `__str__`.
  - `CompanyPersonLink` — `company (FK Company, related_name="person_links")`, `person (FK clients.Client, related_name="company_links")`, `position`, `is_primary`, `linked_by (FK User)`, `created_at`; `unique_together=(company, person)`.

- [ ] **Step 0: Превратить `crm/clients/tests.py` в пакет `tests/`**

Django находит и `tests.py`, и пакет `tests/`, но не оба сразу. Существующий `crm/clients/tests.py` переносим в пакет.

Run:
```bash
cd /home/shalyn42k/Dev/zetom_crm
mkdir -p crm/clients/tests
git mv crm/clients/tests.py crm/clients/tests/test_views.py
touch crm/clients/tests/__init__.py
```
Проверить что старые тесты всё ещё видны:
```bash
python manage.py test crm.clients.tests.test_views -v 1
```
Expected: PASS (или те же результаты, что и раньше — импорты внутри файла остаются валидны).

- [ ] **Step 1: Написать падающий тест на `Company` + `CompanyPersonLink`**

Create `crm/clients/tests/test_company.py`:
```python
# claude
from django.contrib.auth.models import User
from django.test import TestCase

from crm.clients.models import Client, Company, CompanyPersonLink, SupplierType


class CompanyModelTest(TestCase):
    def test_nip_normalized_on_clean(self):
        c = Company(name="Zetom", nip="123-456-32-18")
        c.clean()
        self.assertEqual(c.nip, "1234563218")

    def test_str_shows_name_and_nip(self):
        c = Company.objects.create(name="Zetom", nip="1234563218")
        self.assertEqual(str(c), "Zetom (1234563218)")

    def test_supplier_type_choices(self):
        self.assertEqual(SupplierType.LOCAL, "lokalny")
        self.assertEqual(SupplierType.INTERNATIONAL, "miedzynarodowy")


class CompanyPersonLinkTest(TestCase):
    def test_link_person_to_company_with_position(self):
        company = Company.objects.create(name="Zetom", nip="1234563218")
        person = Client.objects.create(first_name="Jan", last_name="Kowalski")
        user = User.objects.create(username="staff")
        link = CompanyPersonLink.objects.create(
            company=company, person=person, position="Kierownik",
            is_primary=True, linked_by=user,
        )
        self.assertEqual(person.company_links.count(), 1)
        self.assertEqual(company.person_links.first().position, "Kierownik")
        self.assertTrue(link.is_primary)

    def test_unique_company_person(self):
        from django.db import IntegrityError, transaction
        company = Company.objects.create(name="Zetom")
        person = Client.objects.create(first_name="Jan")
        CompanyPersonLink.objects.create(company=company, person=person)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CompanyPersonLink.objects.create(company=company, person=person)
```

- [ ] **Step 2: Прогнать тест — убедиться что падает**

Run: `python manage.py test crm.clients.tests.test_company -v 2`
Expected: FAIL — `ImportError: cannot import name 'Company'`.

- [ ] **Step 3: Добавить модели в `crm/clients/models.py`**

Append в конец файла:
```python
# claude
class SupplierType(models.TextChoices):
    LOCAL = "lokalny", _("Lokalny")
    REGIONAL = "regionalny", _("Regionalny")
    INTERNATIONAL = "miedzynarodowy", _("Międzynarodowy")


# claude
class Company(models.Model):
    """Фирма (Klient/Firma). Нормализованная сущность взамен текст-полей
    company_name/company_nip на Client."""

    name = models.CharField(_("Name"), max_length=255)
    short_name = models.CharField(_("Short name"), max_length=255, blank=True)
    full_name = models.CharField(_("Full name"), max_length=500, blank=True)

    nip = models.CharField(
        _("NIP"), max_length=20, blank=True, null=True, db_index=True,
        validators=[validate_nip],
    )
    regon = models.CharField(_("REGON"), max_length=14, blank=True)
    type_supplier = models.CharField(
        _("Supplier type"), max_length=20, choices=SupplierType.choices, blank=True,
    )

    country = models.CharField(_("Country"), max_length=100, blank=True)
    city = models.CharField(_("City"), max_length=100, blank=True)
    voivodeship = models.CharField(_("Voivodeship"), max_length=100, blank=True)
    post_code = models.CharField(_("Post code"), max_length=20, blank=True)
    street = models.CharField(_("Street"), max_length=255, blank=True)

    phone = PhoneNumberField(_("Phone"), null=True, blank=True)
    email = models.EmailField(_("Email"), blank=True)

    comments = models.TextField(_("Comments"), blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Company")
        verbose_name_plural = _("Companies")

    def clean(self):
        super().clean()
        if self.nip:
            self.nip = normalize_nip(self.nip)

    def __str__(self):
        if self.nip:
            return f"{self.name} ({self.nip})"
        return self.name or f"Company #{self.pk}"


# claude
class CompanyPersonLink(models.Model):
    """M2M связь Company ↔ Client(=Person) с должностью. Человек может быть в
    нескольких фирмах (несколько связей)."""

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="person_links",
        verbose_name=_("Company"),
    )
    person = models.ForeignKey(
        "clients.Client", on_delete=models.CASCADE, related_name="company_links",
        verbose_name=_("Person"),
    )
    position = models.CharField(_("Position"), max_length=255, blank=True)
    is_primary = models.BooleanField(_("Primary contact"), default=False)
    linked_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name=_("Linked by"),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Company contact")
        verbose_name_plural = _("Company contacts")
        constraints = [
            models.UniqueConstraint(
                fields=["company", "person"], name="uniq_company_person",
            ),
        ]

    def __str__(self):
        return f"{self.person_id} @ {self.company_id}"
```

- [ ] **Step 4: Сгенерировать и применить schema-миграцию**

Run:
```bash
python manage.py makemigrations clients
python manage.py migrate clients
```
Expected: создан `crm/clients/migrations/0006_company_companypersonlink.py`; миграция применяется без ошибок.

- [ ] **Step 5: Прогнать тест — убедиться что проходит**

Run: `python manage.py test crm.clients.tests.test_company -v 2`
Expected: PASS (4 теста).

- [ ] **Step 6: Коммит**

```bash
git add crm/clients/models.py crm/clients/migrations/0006_*.py crm/clients/tests/
git commit -m "feat(clients): add Company + CompanyPersonLink models (phase 1)"
```

---

### Task 2: FK `RequestMain.company`

**Files:**
- Modify: `crm/zetom/models.py` (класс `RequestMain`, добавить поле после `owners`/`clients`)
- Test: `crm/zetom/tests/test_requestmain_company.py` (создать)

**Interfaces:**
- Consumes: `Company` из Task 1.
- Produces: `RequestMain.company` (FK → `clients.Company`, `null=True`, `blank=True`, `on_delete=SET_NULL`, `related_name="requests"`).

- [ ] **Step 1: Написать падающий тест**

Create `crm/zetom/tests/test_requestmain_company.py`:
```python
# claude
from django.test import TestCase

from crm.clients.models import Company
from crm.zetom.models import RequestMain


class RequestMainCompanyFKTest(TestCase):
    def test_company_fk_nullable(self):
        req = RequestMain.objects.create()
        self.assertIsNone(req.company)

    def test_company_reverse_related_name(self):
        company = Company.objects.create(name="Zetom")
        req = RequestMain.objects.create(company=company)
        self.assertEqual(company.requests.count(), 1)
        self.assertEqual(company.requests.first(), req)
```

- [ ] **Step 2: Прогнать — убедиться что падает**

Run: `python manage.py test crm.zetom.tests.test_requestmain_company -v 2`
Expected: FAIL — `TypeError: ... unexpected keyword argument 'company'` / `AttributeError`.

- [ ] **Step 3: Добавить поле в `RequestMain`**

В `crm/zetom/models.py`, в классе `RequestMain` (рядом с `clients = models.ManyToManyField(...)`), добавить:
```python
    # claude — нормализованная привязка заявки к фирме (в дополнение к
    # снапшот-полям company_name/company_nip на самой заявке). Nullable:
    # заявка от частного лица без фирмы её не имеет.
    company = models.ForeignKey(
        "clients.Company",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requests",
        verbose_name=_("Company"),
    )
```
Проверить что `_` (gettext_lazy) уже импортирован в файле (да — используется в других полях).

- [ ] **Step 4: Миграция + применить**

Run:
```bash
python manage.py makemigrations zetom
python manage.py migrate zetom
```
Expected: создан `crm/zetom/migrations/0013_requestmain_company.py`; применяется чисто.

- [ ] **Step 5: Прогнать тест — проходит**

Run: `python manage.py test crm.zetom.tests.test_requestmain_company -v 2`
Expected: PASS (2 теста).

- [ ] **Step 6: Коммит**

```bash
git add crm/zetom/models.py crm/zetom/migrations/0013_*.py crm/zetom/tests/test_requestmain_company.py
git commit -m "feat(zetom): add RequestMain.company FK (phase 1)"
```

---

### Task 3: Data-migration бэкфилл (Company ← Client.company_*, связи, RequestMain.company)

**Files:**
- Create: `crm/clients/backfill.py` (функция бэкфилла, принимает классы моделей)
- Create: `crm/clients/migrations/0007_backfill_companies.py` (RunPython, empty-скелет через makemigrations)
- Test: `crm/clients/tests/test_backfill.py`

**Interfaces:**
- Consumes: `Company`, `CompanyPersonLink` (Task 1), `RequestMain.company` (Task 2), существующие `Client`, `RequestClientLink`.
- Produces: `crm.clients.backfill.backfill_companies(Client, Company, CompanyPersonLink, RequestMain, RequestClientLink)` — идемпотентно (повторный вызов не плодит дубли).

Логика:
1. Для каждого `Client` с непустым `company_name` или `company_nip`:
   - ключ дедупа: нормализованный `company_nip` (если валиден), иначе `company_name.strip().lower()`.
   - `get_or_create` `Company` по этому ключу (nip → поле `nip`; name → поле `name`), перенести `company_name`→`name`, `address`→в `street`/оставить пустым (адрес Client — свободный текст, кладём в `Company.comments` чтобы не терять).
   - `get_or_create` `CompanyPersonLink(company, person=client)`.
2. Для каждого `RequestClientLink`: если у `request` (RequestMain) ещё нет `company`, и связанный `client` имеет ровно одну `Company` — проставить `request.company`.

- [ ] **Step 1: Написать падающий тест бэкфилла**

Create `crm/clients/tests/test_backfill.py`:
```python
# claude
from django.test import TestCase

from crm.clients.backfill import backfill_companies
from crm.clients.models import Client, Company, CompanyPersonLink
from crm.zetom.models import RequestClientLink, RequestMain


def _run():
    backfill_companies(Client, Company, CompanyPersonLink, RequestMain, RequestClientLink)


class BackfillTest(TestCase):
    def test_creates_company_from_client_nip(self):
        Client.objects.create(
            first_name="Jan", last_name="Kowalski",
            company_name="Zetom", company_nip="1234563218",
        )
        _run()
        self.assertEqual(Company.objects.count(), 1)
        company = Company.objects.get()
        self.assertEqual(company.name, "Zetom")
        self.assertEqual(company.nip, "1234563218")
        self.assertEqual(CompanyPersonLink.objects.count(), 1)

    def test_dedup_same_nip_two_people(self):
        Client.objects.create(first_name="A", company_name="Zetom", company_nip="1234563218")
        Client.objects.create(first_name="B", company_name="Zetom SA", company_nip="123-456-32-18")
        _run()
        self.assertEqual(Company.objects.count(), 1)          # один NIP → одна фирма
        self.assertEqual(CompanyPersonLink.objects.count(), 2)  # оба привязаны

    def test_person_without_company_skipped(self):
        Client.objects.create(first_name="Solo")  # ни name ни nip
        _run()
        self.assertEqual(Company.objects.count(), 0)
        self.assertEqual(CompanyPersonLink.objects.count(), 0)

    def test_sets_requestmain_company(self):
        client = Client.objects.create(company_name="Zetom", company_nip="1234563218")
        req = RequestMain.objects.create()
        RequestClientLink.objects.create(request=req, client=client)
        _run()
        req.refresh_from_db()
        self.assertEqual(req.company, Company.objects.get())

    def test_idempotent(self):
        Client.objects.create(company_name="Zetom", company_nip="1234563218")
        _run()
        _run()
        self.assertEqual(Company.objects.count(), 1)
        self.assertEqual(CompanyPersonLink.objects.count(), 1)
```

- [ ] **Step 2: Прогнать — падает**

Run: `python manage.py test crm.clients.tests.test_backfill -v 2`
Expected: FAIL — `ModuleNotFoundError: crm.clients.backfill`.

- [ ] **Step 3: Написать функцию бэкфилла**

Create `crm/clients/backfill.py`:
```python
# claude
"""Бэкфилл нормализованных Company/связей из легаси текст-полей Client.
Функция принимает классы моделей аргументами: тот же код вызывается из
data-миграции (через apps.get_model) и из теста (реальные модели)."""
from django.core.exceptions import ValidationError

from crm.clients.validators import normalize_nip


def _dedup_key(client):
    """Ключ дедупа фирмы: нормализованный NIP если валиден, иначе имя."""
    if client.company_nip:
        try:
            return ("nip", normalize_nip(client.company_nip))
        except ValidationError:
            pass
    if client.company_name:
        return ("name", client.company_name.strip().lower())
    return None


def backfill_companies(Client, Company, CompanyPersonLink, RequestMain, RequestClientLink):
    # 1. Company + связи из Client.company_*
    cache = {}  # dedup_key -> Company
    for client in Client.objects.all():
        key = _dedup_key(client)
        if key is None:
            continue
        company = cache.get(key)
        if company is None:
            kind, value = key
            if kind == "nip":
                lookup = {"nip": value}
                defaults = {"name": client.company_name or value, "comments": client.address or ""}
            else:  # dedup by name
                lookup = {"name": client.company_name.strip()}
                defaults = {"comments": client.address or ""}
            company, _created = Company.objects.get_or_create(**lookup, defaults=defaults)
            cache[key] = company
        CompanyPersonLink.objects.get_or_create(company=company, person=client)

    # 2. RequestMain.company из связей (если однозначно)
    for link in RequestClientLink.objects.select_related("request", "client"):
        req = link.request
        if req.company_id is not None:
            continue
        companies = list(
            CompanyPersonLink.objects.filter(person=link.client)
            .values_list("company_id", flat=True)
        )
        if len(set(companies)) == 1:
            req.company_id = companies[0]
            req.save(update_fields=["company"])
```

- [ ] **Step 4: Прогнать тест — проходит**

Run: `python manage.py test crm.clients.tests.test_backfill -v 2`
Expected: PASS (5 тестов).

- [ ] **Step 5: Создать пустую data-миграцию и подключить функцию**

Run:
```bash
python manage.py makemigrations clients --empty --name backfill_companies
```
Отредактировать созданный `crm/clients/migrations/0007_backfill_companies.py`:
```python
# claude
from django.db import migrations

from crm.clients.backfill import backfill_companies


def forwards(apps, schema_editor):
    backfill_companies(
        apps.get_model("clients", "Client"),
        apps.get_model("clients", "Company"),
        apps.get_model("clients", "CompanyPersonLink"),
        apps.get_model("zetom", "RequestMain"),
        apps.get_model("zetom", "RequestClientLink"),
    )


def backwards(apps, schema_editor):
    # Реверс: снять company с заявок, удалить связи и компании.
    apps.get_model("zetom", "RequestMain").objects.update(company=None)
    apps.get_model("clients", "CompanyPersonLink").objects.all().delete()
    apps.get_model("clients", "Company").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("clients", "0006_company_companypersonlink"),
        ("zetom", "0013_requestmain_company"),
    ]
    operations = [migrations.RunPython(forwards, backwards)]
```
Примечание: `backfill.py` импортирует только `normalize_nip` (не модели), поэтому импорт в миграции безопасен; сами модели приходят через `apps.get_model`.

- [ ] **Step 6: Применить миграцию на дев-БД и проверить**

Run:
```bash
python manage.py migrate clients
```
Expected: `Applying clients.0007_backfill_companies... OK`.
Проверить обратимость (на дев-БД):
```bash
python manage.py migrate clients 0006
python manage.py migrate clients 0007
```
Expected: обе стороны применяются без ошибок.

- [ ] **Step 7: Коммит**

```bash
git add crm/clients/backfill.py crm/clients/migrations/0007_*.py crm/clients/tests/test_backfill.py
git commit -m "feat(clients): backfill Company/links from legacy Client fields (phase 1)"
```

---

### Task 4: Admin-регистрация `Company` + inline контактов

**Files:**
- Modify: `crm/clients/admin.py` (добавить `CompanyAdmin` + `CompanyPersonLinkInline`; НЕ трогать существующий `ClientAdmin`)
- Test: `crm/clients/tests/test_company_admin.py`

**Interfaces:**
- Consumes: `Company`, `CompanyPersonLink` (Task 1); RBAC-хелпер `crm.users.utils.user_has_perm` (используется в `ClientAdmin`).
- Produces: `Company` зарегистрирована в admin; inline `CompanyPersonLink` на карточке фирмы. Права — те же RBAC-коды `view_clients`/`edit_clients`/`delete_clients`.

- [ ] **Step 1: Написать падающий тест регистрации**

Create `crm/clients/tests/test_company_admin.py`:
```python
# claude
from django.contrib import admin
from django.test import TestCase

from crm.clients.models import Company


class CompanyAdminRegisteredTest(TestCase):
    def test_company_registered(self):
        self.assertIn(Company, admin.site._registry)

    def test_company_admin_has_contact_inline(self):
        model_admin = admin.site._registry[Company]
        inline_models = [inline.model for inline in model_admin.inlines]
        from crm.clients.models import CompanyPersonLink
        self.assertIn(CompanyPersonLink, inline_models)
```

- [ ] **Step 2: Прогнать — падает**

Run: `python manage.py test crm.clients.tests.test_company_admin -v 2`
Expected: FAIL — `KeyError: Company` (не зарегистрирована).

- [ ] **Step 3: Добавить admin-классы**

В `crm/clients/admin.py` обновить импорт моделей и добавить классы. Импорт:
```python
from .models import Client, ClientInteraction, ClientType, Company, CompanyPersonLink
```
Добавить перед `ClientInteractionAdmin` (в конец файла):
```python
# claude — контактные лица фирмы прямо в карточке Company (Osoby kontaktowe).
class CompanyPersonLinkInline(admin.TabularInline):
    model = CompanyPersonLink
    extra = 0
    fields = ("person", "position", "is_primary", "linked_by")
    autocomplete_fields = ("person",)
    readonly_fields = ("created_at",)


# claude — базовая регистрация фирмы (Klient/Firma). Кастомные List/Detail
# поверхности — Фаза 3. Права через те же RBAC-коды, что и ClientAdmin.
@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "nip", "type_supplier", "city", "phone", "email")
    search_fields = ("name", "short_name", "full_name", "nip")
    list_filter = ("type_supplier",)
    inlines = [CompanyPersonLinkInline]

    def has_module_permission(self, request):
        return user_has_perm(request.user, "view_clients")

    def has_view_permission(self, request, obj=None):
        return user_has_perm(request.user, "view_clients")

    def has_add_permission(self, request):
        return user_has_perm(request.user, "edit_clients")

    def has_change_permission(self, request, obj=None):
        return user_has_perm(request.user, "edit_clients")

    def has_delete_permission(self, request, obj=None):
        return user_has_perm(request.user, "delete_clients")
```
Примечание: `CompanyPersonLinkInline` использует `autocomplete_fields = ("person",)` — для этого `ClientAdmin` уже имеет `search_fields` (есть). Ок.

- [ ] **Step 4: Прогнать тест — проходит**

Run: `python manage.py test crm.clients.tests.test_company_admin -v 2`
Expected: PASS (2 теста).

- [ ] **Step 5: Смоук — сервер поднимается, система-чек чист**

Run: `python manage.py check`
Expected: `System check identified no issues`.

- [ ] **Step 6: Коммит**

```bash
git add crm/clients/admin.py crm/clients/tests/test_company_admin.py
git commit -m "feat(clients): register Company admin with contacts inline (phase 1)"
```

---

### Task 5: i18n новых строк (PL + EN) + финальная проверка фазы

**Files:**
- Modify: `locale/pl/LC_MESSAGES/django.po`, `locale/en/LC_MESSAGES/django.po` (генерятся)

**Interfaces:** нет кода; закрывает DoD по i18n и прогоняет всю затронутую тестовую поверхность.

- [ ] **Step 1: Собрать новые строки**

Run:
```bash
python manage.py makemessages -l pl -l en
```
Expected: в `.po` появились msgid: `Company`, `Companies`, `Supplier type`, `Lokalny`, `Regionalny`, `Międzynarodowy`, `REGON`, `Voivodeship`, `Post code`, `Company contact`, `Company contacts`, `Primary contact`, `Position`, `Linked by`, `Person`.

- [ ] **Step 2: Перевести новые msgid**

Заполнить `msgstr` в обоих `.po` (PL — польские, EN — английские). Польские значения enum совпадают с ключами (`Lokalny`/`Regionalny`/`Międzynarodowy`). Пример для PL `Company` → `Firma`, `Company contacts` → `Osoby kontaktowe`, `Position` → `Stanowisko`, `Primary contact` → `Główny kontakt`.

- [ ] **Step 3: Скомпилировать**

Run: `python manage.py compilemessages`
Expected: `.mo` собраны без ошибок.

- [ ] **Step 4: Прогнать всю затронутую тестовую поверхность**

Run:
```bash
python manage.py test crm.clients crm.zetom -v 1
```
Expected: все тесты PASS (включая старые VW/дедуп/client — Фаза 1 их не трогала).

- [ ] **Step 5: Проверка целостности миграций**

Run: `python manage.py makemigrations --check --dry-run`
Expected: `No changes detected`.

- [ ] **Step 6: Коммит**

```bash
git add locale/
git commit -m "i18n(clients): translate Company/contact strings PL+EN (phase 1)"
```

---

## Self-Review

**Spec coverage (Фаза 1):**
- Company модель → Task 1 ✅
- CompanyPersonLink M2M → Task 1 ✅
- RequestMain.company FK → Task 2 ✅
- Data-migration бэкфилл → Task 3 ✅
- Admin-регистрация Company + Osoby kontaktowe inline → Task 4 ✅
- i18n PL+EN → Task 5 ✅
- «Client не трогаем в Фазе 1» — соблюдено (rename/удаление полей = Фаза 2) ✅

**Вне Фазы 1 (сознательно):** rename Client→Person, Company-aware search/autofill/VW-дедуп/интейк, удаление company_*/client_type с Person, поверхности #11/#12 — Фазы 2/3.

**Placeholder scan:** код полный в каждом шаге, команды с ожидаемым выводом. ОК.

**Type consistency:** `backfill_companies(Client, Company, CompanyPersonLink, RequestMain, RequestClientLink)` — сигнатура одинакова в тесте (Step 1) и в миграции (Step 5). `related_name`: `Company.person_links`, `Client.company_links`, `Company.requests` — согласованы между Task 1/2 и тестами.

## Риски / точки внимания

- **Идемпотентность бэкфилла** покрыта тестом `test_idempotent` — безопасно гонять повторно на проде.
- **Невалидные легаси-NIP**: `_dedup_key` ловит `ValidationError` и падает на дедуп по имени — фирма всё равно создастся.
- **RequestMain.company ставится только при однозначности** (клиент ровно в одной фирме) — многофирменные случаи остаются `NULL`, доразметятся вручную/в Фазе 2.
- **Адрес Client** кладётся в `Company.comments` чтобы не потерять (у Company структурированный адрес, у Client — свободный текст).
