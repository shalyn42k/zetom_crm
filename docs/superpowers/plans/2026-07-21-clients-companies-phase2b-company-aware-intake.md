# Clients/Companies — Phase 2b (Company-aware intake write path) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перевести интейк (создание/линковку клиента) на нормализованную модель: при создании нового клиента заводить/находить `Company` по NIP и линковать, вместо записи `company_name`/`company_nip` на `Client`; проставлять `RequestMain.company`.

**Architecture:** Общий хелпер `create_person_with_company(...)` в `crm/clients/services.py` создаёт `Client`(человек) + при наличии данных фирмы get/create `Company` (по нормализованному NIP, иначе по имени) + `CompanyPersonLink`, возвращает `(client, company)`. Три интейк-спота (VW-approve `_do_approve`, RequestMain-popup `response_add`, prefill `base.py`) переводятся на него / на чтение из связанной `Company`. Поля `Client.company_*` пока НЕ удаляются (это 2c) — просто перестаём их писать. Снапшот-поля `company_name`/`company_nip` на самих заявках НЕ трогаются.

**Tech Stack:** Django 5.2, PostgreSQL, тесты через `manage.py test` (Django TestCase).

## Global Constraints

- Django 5.2 / Postgres. Тесты: `python manage.py test <path> -v 2` (не pytest; `--keepdb` если ругается на leftover test-DB).
- Python-блоки Claude помечать `# claude`. **НЕ добавлять** `Co-Authored-By: Claude` (проверять сообщение перед коммитом — правило нарушалось).
- Не удалять `Client.company_name`/`company_nip`/`client_type` (это 2c). `ClientForm`/`ClientAdmin` company-поля — тоже 2c.
- Дедуп фирмы: по нормализованному NIP (`normalize_nip`, ловить `ValidationError`), иначе по имени (`name__iexact`, `order_by("id").first()`), иначе фирма не создаётся. Тот же паттерн, что в `crm/clients/backfill.py`.
- `RequestMain.company` ставится только если ещё пуст (`company_id is None`).

---

### Task 1: Хелпер `create_person_with_company`

**Files:**
- Modify: `crm/clients/services.py` (добавить функцию + импорты)
- Test: `crm/clients/tests/test_create_person_with_company.py` (создать)

**Interfaces:**
- Consumes: `Client`, `Company`, `CompanyPersonLink` (Phase 1); `normalize_nip` (validators).
- Produces: `create_person_with_company(*, first_name="", last_name="", phone=None, email="", company_name="", company_nip=None, address="", linked_by=None) -> tuple[Client, Company | None]`.

- [ ] **Step 1: Написать падающий тест**

Create `crm/clients/tests/test_create_person_with_company.py`:
```python
# claude
from django.test import TestCase

from crm.clients.models import Client, Company, CompanyPersonLink
from crm.clients.services import create_person_with_company


class CreatePersonWithCompanyTest(TestCase):
    def test_creates_person_and_company_by_nip(self):
        person, company = create_person_with_company(
            first_name="Jan", last_name="Kowalski",
            company_name="Zetom", company_nip="123-456-32-18", email="j@z.pl",
        )
        self.assertIsInstance(person, Client)
        self.assertEqual(person.first_name, "Jan")
        self.assertIsNotNone(company)
        self.assertEqual(company.nip, "1234563218")          # normalized
        self.assertEqual(company.name, "Zetom")
        self.assertEqual(CompanyPersonLink.objects.filter(company=company, person=person).count(), 1)

    def test_dedups_company_by_nip(self):
        c = Company.objects.create(name="Zetom", nip="1234563218")
        person, company = create_person_with_company(
            first_name="A", company_name="Zetom SA", company_nip="1234563218",
        )
        self.assertEqual(company.pk, c.pk)                    # reused, not duplicated
        self.assertEqual(Company.objects.count(), 1)

    def test_company_by_name_when_no_nip(self):
        person, company = create_person_with_company(
            first_name="A", company_name="NoNipCo",
        )
        self.assertIsNotNone(company)
        self.assertEqual(company.name, "NoNipCo")
        self.assertIsNone(company.nip)

    def test_person_only_when_no_company_info(self):
        person, company = create_person_with_company(first_name="Solo", email="s@s.pl")
        self.assertIsNone(company)
        self.assertEqual(CompanyPersonLink.objects.count(), 0)

    def test_invalid_nip_falls_back_to_name(self):
        person, company = create_person_with_company(
            first_name="A", company_name="BadNipCo", company_nip="not-a-nip",
        )
        self.assertIsNotNone(company)
        self.assertEqual(company.name, "BadNipCo")
        self.assertIsNone(company.nip)                        # invalid NIP dropped
```

- [ ] **Step 2: Прогнать — падает**

Run: `python manage.py test crm.clients.tests.test_create_person_with_company -v 2`
Expected: FAIL — `ImportError: cannot import name 'create_person_with_company'`.

- [ ] **Step 3: Добавить функцию в `crm/clients/services.py`**

Вверху файла в блок импортов добавить (рядом с существующим `from crm.clients.models import Client`):
```python
# claude
from django.core.exceptions import ValidationError

from crm.clients.models import Company, CompanyPersonLink
from crm.clients.validators import normalize_nip
```
В конец файла добавить:
```python
# claude — единая точка создания «человек + (опц.) фирма» для интейка.
# Дедуп фирмы повторяет логику backfill: по NIP, иначе по имени.
def create_person_with_company(
    *, first_name="", last_name="", phone=None, email="",
    company_name="", company_nip=None, address="", linked_by=None,
):
    client = Client.objects.create(
        first_name=first_name or None,
        last_name=last_name or None,
        phone=phone or None,
        email=email or None,
    )

    nip = None
    if company_nip:
        try:
            nip = normalize_nip(company_nip)
        except ValidationError:
            nip = None

    company = None
    if nip:
        company, _created = Company.objects.get_or_create(
            nip=nip,
            defaults={"name": company_name or nip, "comments": address or ""},
        )
    elif company_name:
        stripped = company_name.strip()
        company = Company.objects.filter(name__iexact=stripped).order_by("id").first()
        if company is None:
            company = Company.objects.create(name=stripped, comments=address or "")

    if company is not None:
        CompanyPersonLink.objects.get_or_create(
            company=company, person=client, defaults={"linked_by": linked_by},
        )
    return client, company
```

- [ ] **Step 4: Прогнать — проходит**

Run: `python manage.py test crm.clients.tests.test_create_person_with_company -v 2`
Expected: PASS (5 тестов).

- [ ] **Step 5: Коммит**

```bash
git add crm/clients/services.py crm/clients/tests/test_create_person_with_company.py
git commit -m "feat(clients): create_person_with_company intake helper (phase 2b)"
```

---

### Task 2: VW-approve (`_do_approve`) через хелпер + `RequestMain.company`

**Files:**
- Modify: `crm/zetom/admin/requestnull_validate.py` (`_do_approve`, импорт)
- Test: `crm/zetom/tests/test_vw_approve_company.py` (создать)

**Interfaces:**
- Consumes: `create_person_with_company` (Task 1).
- Produces: при `create_new` в VW создаётся `Client` + `Company`(по NIP/имени) + связь; `new_main.company` проставляется из созданной фирмы (если пуст). `Client.company_*` больше не пишутся.

- [ ] **Step 1: Написать падающий тест (вызов `_do_approve` напрямую)**

Create `crm/zetom/tests/test_vw_approve_company.py`:
```python
# claude
from django.contrib.auth.models import User
from django.test import TestCase

from crm.clients.models import Client, Company, CompanyPersonLink
from crm.zetom.admin.requestnull_validate import _do_approve
from crm.zetom.models import DepartmentsVariants, RequestNull


class VWApproveCompanyTest(TestCase):
    def _cleaned(self, **over):
        base = {
            "departments": [DepartmentsVariants.choices[0][0]],
            "owners": [],
            "link_client_ids": [],
            "create_new": True,
            "new_first_name": "Jan",
            "new_last_name": "Kowalski",
            "new_phone": "+48501600300",
            "new_email": "jan@zetom.pl",
            "new_company_name": "Zetom",
            "new_company_nip": "1234563218",
        }
        base.update(over)
        return base

    def test_approve_creates_company_and_sets_requestmain_company(self):
        rn = RequestNull.objects.create(
            first_name="Jan", last_name="Kowalski",
            phone="+48501600300", email="jan@zetom.pl", company_name="Zetom",
        )
        user = User.objects.create(username="validator")
        new_main = _do_approve(rn, self._cleaned(), user=user)

        company = Company.objects.get(nip="1234563218")
        self.assertEqual(new_main.company_id, company.pk)
        person = Client.objects.get(first_name="Jan")
        self.assertEqual(CompanyPersonLink.objects.filter(company=company, person=person).count(), 1)
        # company_* НЕ записаны на человека
        self.assertFalse(person.company_name)
        self.assertFalse(person.company_nip)
```

- [ ] **Step 2: Прогнать — падает**

Run: `python manage.py test crm.zetom.tests.test_vw_approve_company -v 2`
Expected: FAIL — `new_main.company_id` は None (сейчас `_do_approve` пишет `company_name`/`company_nip` на Client, `RequestMain.company` не ставит) и/или `person.company_name == "Zetom"`.

- [ ] **Step 3: Переписать `create_new` блок в `_do_approve`**

В `crm/zetom/admin/requestnull_validate.py` добавить импорт вверху (рядом с другими `from crm.clients...` / сервисами):
```python
# claude
from crm.clients.services import create_person_with_company
```
Заменить блок (строки создания клиента при `create_new`):
```python
    if cleaned.get("create_new"):
        clients.append(Client.objects.create(
            first_name=cleaned.get("new_first_name") or rn.first_name,
            last_name=cleaned.get("new_last_name") or rn.last_name,
            company_name=cleaned.get("new_company_name") or rn.company_name,
            company_nip=cleaned.get("new_company_nip") or None,
            phone=cleaned.get("new_phone") or rn.phone,
            email=cleaned.get("new_email") or rn.email,
        ))
```
на:
```python
    if cleaned.get("create_new"):
        # claude — интейк создаёт человека + (опц.) нормализованную Company,
        # вместо записи company_* на Client. Фирму вешаем на new_main.
        person, company = create_person_with_company(
            first_name=cleaned.get("new_first_name") or rn.first_name,
            last_name=cleaned.get("new_last_name") or rn.last_name,
            phone=cleaned.get("new_phone") or rn.phone,
            email=cleaned.get("new_email") or rn.email,
            company_name=cleaned.get("new_company_name") or rn.company_name,
            company_nip=cleaned.get("new_company_nip") or None,
            linked_by=user,
        )
        clients.append(person)
        if company is not None and new_main.company_id is None:
            new_main.company = company
            new_main.save(update_fields=["company"])
```

- [ ] **Step 4: Прогнать — проходит**

Run: `python manage.py test crm.zetom.tests.test_vw_approve_company -v 2`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add crm/zetom/admin/requestnull_validate.py crm/zetom/tests/test_vw_approve_company.py
git commit -m "refactor(zetom): VW approve creates Company + sets RequestMain.company (phase 2b)"
```

---

### Task 3: RequestMain popup (`response_add`) через хелпер + `RequestMain.company`

**Files:**
- Modify: `crm/zetom/admin/requestmain.py` (`response_add`, импорт)
- Test: `crm/zetom/tests/test_requestmain_popup_company.py` (создать)

**Interfaces:**
- Consumes: `create_person_with_company` (Task 1).
- Produces: popup «create new» на RequestMain создаёт `Client` + `Company` + связь + `RequestClientLink`; ставит `obj.company`.

- [ ] **Step 1: Написать падающий тест (RequestFactory POST в `response_add`)**

Create `crm/zetom/tests/test_requestmain_popup_company.py`:
```python
# claude
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from crm.clients.models import Client, Company, CompanyPersonLink
from crm.zetom.admin.requestmain import RequestMainAdmin
from crm.zetom.models import RequestClientLink, RequestMain


class RequestMainPopupCompanyTest(TestCase):
    def test_popup_create_new_makes_company_and_links(self):
        admin = RequestMainAdmin(RequestMain, AdminSite())
        user = User.objects.create_superuser("staff", "s@s.pl", "pass12345")
        obj = RequestMain.objects.create(
            first_name="Jan", last_name="Kowalski",
            company_name="Zetom", company_nip="1234563218",
        )
        rf = RequestFactory()
        req = rf.post("/", {
            "popup_create_new": "1",
            "first_name": "Jan", "last_name": "Kowalski",
            "company_name": "Zetom", "company_nip": "1234563218",
            "phone": "+48501600300", "email": "jan@zetom.pl",
        })
        req.user = user
        # response_add редиректит — нам важны сайд-эффекты
        admin.response_add(req, obj)

        company = Company.objects.get(nip="1234563218")
        obj.refresh_from_db()
        self.assertEqual(obj.company_id, company.pk)
        person = Client.objects.get(first_name="Jan")
        self.assertTrue(RequestClientLink.objects.filter(request=obj, client=person).exists())
        self.assertEqual(CompanyPersonLink.objects.filter(company=company, person=person).count(), 1)
```
(Примечание: если `RequestMainAdmin` называется иначе — проверить имя класса в `requestmain.py` и поправить импорт/использование.)

- [ ] **Step 2: Прогнать — падает**

Run: `python manage.py test crm.zetom.tests.test_requestmain_popup_company -v 2`
Expected: FAIL — `obj.company_id` None / Company не создана (сейчас пишется на Client).

- [ ] **Step 3: Переписать `popup_create_new` блок в `response_add`**

В `crm/zetom/admin/requestmain.py` добавить импорт вверху:
```python
# claude
from crm.clients.services import create_person_with_company
```
Заменить блок:
```python
        if request.POST.get("popup_create_new"):
            cl = Client.objects.create(
                first_name=request.POST.get("first_name") or obj.first_name,
                last_name=request.POST.get("last_name") or obj.last_name,
                company_name=request.POST.get("company_name") or obj.company_name,
                company_nip=request.POST.get("company_nip") or obj.company_nip or None,
                phone=request.POST.get("phone") or obj.phone,
                email=request.POST.get("email") or obj.email,
            )
            RequestClientLink.objects.get_or_create(
                request=obj, client=cl, defaults={"linked_by": request.user}
            )
```
на:
```python
        if request.POST.get("popup_create_new"):
            # claude — человек + (опц.) нормализованная Company вместо company_* на Client.
            cl, company = create_person_with_company(
                first_name=request.POST.get("first_name") or obj.first_name,
                last_name=request.POST.get("last_name") or obj.last_name,
                phone=request.POST.get("phone") or obj.phone,
                email=request.POST.get("email") or obj.email,
                company_name=request.POST.get("company_name") or obj.company_name,
                company_nip=request.POST.get("company_nip") or obj.company_nip or None,
                linked_by=request.user,
            )
            RequestClientLink.objects.get_or_create(
                request=obj, client=cl, defaults={"linked_by": request.user}
            )
            if company is not None and obj.company_id is None:
                obj.company = company
                obj.save(update_fields=["company"])
```

- [ ] **Step 4: Прогнать — проходит**

Run: `python manage.py test crm.zetom.tests.test_requestmain_popup_company -v 2`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add crm/zetom/admin/requestmain.py crm/zetom/tests/test_requestmain_popup_company.py
git commit -m "refactor(zetom): RequestMain popup creates Company + sets company (phase 2b)"
```

---

### Task 4: Prefill «Create new» (`base.py`) из связанной `Company`

**Files:**
- Modify: `crm/zetom/admin/base.py` (`get_changeform_initial_data`)
- Test: `crm/zetom/tests/test_prefill_from_company.py` (создать)

**Interfaces:**
- Consumes: `Client.company_links` → `Company` (Phase 1).
- Produces: prefill снапшота заявки берёт `company_name`/`company_nip` из связанной с клиентом `Company`, а не из `Client.company_*`.

- [ ] **Step 1: Написать падающий тест**

Create `crm/zetom/tests/test_prefill_from_company.py`:
```python
# claude
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from crm.clients.models import Client, Company, CompanyPersonLink
from crm.zetom.admin.requestmain import RequestMainAdmin
from crm.zetom.models import RequestMain


class PrefillFromCompanyTest(TestCase):
    def test_prefill_pulls_company_from_link(self):
        person = Client.objects.create(first_name="Jan", last_name="Kowalski")
        company = Company.objects.create(name="Zetom", nip="1234563218")
        CompanyPersonLink.objects.create(company=company, person=person)

        admin = RequestMainAdmin(RequestMain, AdminSite())
        rf = RequestFactory()
        req = rf.get("/add/", {"client": str(person.pk)})
        req.user = User.objects.create_superuser("staff", "s@s.pl", "pass12345")

        initial = admin.get_changeform_initial_data(req)
        self.assertEqual(initial["first_name"], "Jan")
        self.assertEqual(initial["company_name"], "Zetom")
        self.assertEqual(initial["company_nip"], "1234563218")
```

- [ ] **Step 2: Прогнать — падает**

Run: `python manage.py test crm.zetom.tests.test_prefill_from_company -v 2`
Expected: FAIL — `initial["company_name"]` пуст/`KeyError` (сейчас читается `client.company_name`, которого у нового человека нет).

- [ ] **Step 3: Переписать prefill в `base.py`**

В `crm/zetom/admin/base.py`, `get_changeform_initial_data`, заменить блок:
```python
            client = Client.objects.filter(pk=client_id).first()
            if client:
                initial.update({
                    "first_name": client.first_name,
                    "last_name": client.last_name,
                    "company_name": client.company_name,
                    "company_nip": client.company_nip,
                    "phone": client.phone,
                    "email": client.email,
                })
```
на:
```python
            client = Client.objects.filter(pk=client_id).first()
            if client:
                # claude — фирменные поля снапшота берём из связанной Company
                # (company_* уезжают с Client в 2c).
                link = client.company_links.first()
                company = link.company if link else None
                initial.update({
                    "first_name": client.first_name,
                    "last_name": client.last_name,
                    "company_name": company.name if company else "",
                    "company_nip": company.nip if company else "",
                    "phone": client.phone,
                    "email": client.email,
                })
```

- [ ] **Step 4: Прогнать — проходит**

Run: `python manage.py test crm.zetom.tests.test_prefill_from_company -v 2`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add crm/zetom/admin/base.py crm/zetom/tests/test_prefill_from_company.py
git commit -m "refactor(zetom): prefill request snapshot from linked Company (phase 2b)"
```

---

### Task 5: Верификация под-этапа 2b

- [ ] **Step 1: Прогнать всю затронутую поверхность**

Run:
```bash
python manage.py test crm.clients crm.zetom -v 1
```
Expected: PASS, КРОМЕ 1 известного pre-existing фейла `crm.zetom.tests.test_admin.ApproveNullAdminActionTests.test_approve_creates_main_sends_notification_and_redirects` (stale mock.patch, вне скоупа). Новых фейлов нет → `FAILED (errors=1)`.

- [ ] **Step 2: Проверка миграций**

Run: `python manage.py makemigrations --check --dry-run`
Expected: `No changes detected` (2b — только код).

---

## Self-Review

**Spec coverage (2b):**
- Общий хелпер create/link Company → Task 1 ✅
- VW-approve интейк → Task 2 ✅
- RequestMain popup интейк → Task 3 ✅
- Prefill из Company → Task 4 ✅
- `Client.company_*` больше не пишутся интейком (но не удалены — 2c) ✅

**Вне 2b:** удаление полей `company_*`/`client_type` + `ClientForm`/`ClientAdmin` company-поля/сегмент + очистка company-only строк + UI-лейбл Osoba (всё 2c); поверхности #11/#12 (Phase 3).

**Placeholder scan:** код полный в каждом шаге; команды с ожидаемым выводом. Единственная явная проверка — имя класса `RequestMainAdmin` (Task 3/4 Step 1): исполнитель сверяет фактическое имя в `requestmain.py` и правит импорт при расхождении.

**Type consistency:** `create_person_with_company(*, ...) -> (Client, Company|None)` — сигнатура одна в Task 1 (определение) и Task 2/3 (вызовы). `company_links`/`CompanyPersonLink`/`Company.nip`/`Company.name` — имена из Phase 1. `RequestMain.company`/`company_id` — из Phase 1. Дедуп-логика хелпера идентична `backfill.py` (по NIP → по имени).

## Риски / точки внимания

- **Хелпер дублирует дедуп-логику `backfill.py`** осознанно (разные контексты: миграция на классах-аргументах vs рантайм на реальных моделях). Если ревьюер предложит вынести общую логику — можно, но не обязательно для 2b.
- **`RequestMainAdmin`** — сверить фактическое имя класса (Task 3/4).
- **1 pre-existing фейл** (`test_approve_...`) остаётся — вне скоупа.
- **`RequestMain.company` ставится только если пуст** — при нескольких create-new или уже проставленной фирме первая выигрывает; многофирменные кейсы доразметятся в UI (Phase 3).
