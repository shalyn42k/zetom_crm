# Clients/Companies — Phase 2a (Company-aware read layer) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Переписать read-консьюмеры, которые сейчас читают `Client.company_nip`/`company_name`, на источник `Company` (через `CompanyPersonLink`) — VW-дедуп (`duplicate_matcher`) и search/autofill (`views.py`) — БЕЗ переименования Client и БЕЗ удаления полей (это 2c).

**Architecture:** Rename `Client→Person` отменён — класс остаётся `Client` (= человек). После Phase 1 у `Client` есть reverse `company_links` (→ `CompanyPersonLink` → `Company`). 2a меняет ТОЛЬКО чтение сигналов NIP/название-фирмы: раньше брались с `Client.company_*`, теперь с привязанных `Company`. Поля `company_name`/`company_nip` на `Client` пока остаются (fallback не нужен — Phase 1 забэкфиллил Company из них, данные эквивалентны). Снапшот-поля `company_name`/`company_nip` на самих заявках (`RequestNull`/`RequestMain`) НЕ трогаются.

**Tech Stack:** Django 5.2, PostgreSQL, тесты через `manage.py test` (Django TestCase).

## Global Constraints

- Django 5.2 / Postgres. Тесты: `python manage.py test <path> -v 2` (не pytest). Если ругается на leftover test-DB интерактивно — добавить `--keepdb`.
- Python-блоки, написанные Claude, помечать `# claude` над блоком.
- Коммиты частые, по задаче. **НЕ добавлять** `Co-Authored-By: Claude` в коммиты (проверять сообщение перед коммитом).
- Новый user-facing текст — `gettext_lazy as _` (в этом под-этапе новых строк нет).
- Source of truth для NIP/названия фирмы человека — `Company` через `Client.company_links.all()[].company`. Человек может быть в нескольких фирмах → сигнал матчится если ЛЮБАЯ привязанная фирма совпала.
- Не удалять `Client.company_name`/`company_nip`/`client_type` в этом под-этапе (это Phase 2c).

---

### Task 1: Company-aware `duplicate_matcher` (VW Client-дедуп)

**Files:**
- Modify: `crm/zetom/services/duplicate_matcher.py` (`_candidate_queryset`, `_score_one`)
- Test: `crm/zetom/tests/test_duplicate_matcher.py` (создать — матчер сейчас без теста)

**Interfaces:**
- Consumes: `Client.company_links` → `CompanyPersonLink.company` → `Company.nip`/`name` (Phase 1); `Company` из `crm.clients.models`.
- Produces: `find_candidates(rn)` матчит NIP/название фирмы из привязанных `Company`, а не из `Client.company_*`. Публичная сигнатура (`find_candidates`, `Candidate`, `Badge`, `BADGE_*`) без изменений.

- [ ] **Step 1: Написать падающий тест матчера (Company-aware)**

Create `crm/zetom/tests/test_duplicate_matcher.py`:
```python
# claude
from django.test import TestCase

from crm.clients.models import Client, Company, CompanyPersonLink
from crm.zetom.models import RequestNull
from crm.zetom.services.duplicate_matcher import (
    BADGE_SAME_COMPANY, BADGE_SAME_NIP, find_candidates,
)


def _person_in_company(nip="1234567890", name="Zetom", **person):
    company = Company.objects.create(name=name, nip=nip)
    client = Client.objects.create(**person)
    CompanyPersonLink.objects.create(company=company, person=client)
    return client


class DuplicateMatcherCompanyAwareTest(TestCase):
    def test_same_nip_from_linked_company(self):
        _person_in_company(nip="1234567890", first_name="Jan", last_name="Kowalski")
        rn = RequestNull.objects.create(
            first_name="X", last_name="Y", company_nip="1234567890",
        )
        results = find_candidates(rn)
        self.assertTrue(results)
        self.assertIn(BADGE_SAME_NIP, [b.kind for b in results[0].badges])

    def test_same_company_name_from_linked_company(self):
        _person_in_company(nip="", name="Zetom", first_name="Jan", last_name="Kowalski")
        rn = RequestNull.objects.create(
            first_name="X", last_name="Y", company_name="Zetom",
        )
        results = find_candidates(rn)
        self.assertTrue(results)
        self.assertIn(BADGE_SAME_COMPANY, [b.kind for b in results[0].badges])

    def test_person_without_company_gets_no_nip_badge(self):
        Client.objects.create(first_name="Solo", last_name="NoCompany")
        rn = RequestNull.objects.create(
            first_name="Solo", last_name="NoCompany", company_nip="1234567890",
        )
        results = find_candidates(rn)
        for c in results:
            self.assertNotIn(BADGE_SAME_NIP, [b.kind for b in c.badges])

    def test_nip_only_prefilter_catches_candidate(self):
        # человек без совпадений по phone/email/name, только NIP через фирму
        _person_in_company(nip="9999999999", first_name="Zzz", last_name="Qqq")
        rn = RequestNull.objects.create(
            first_name="Aaa", last_name="Bbb", company_nip="9999999999",
        )
        results = find_candidates(rn)
        self.assertTrue(results)  # найден по NIP фирмы, хотя имя/контакты разные
```

- [ ] **Step 2: Прогнать — падает**

Run: `python manage.py test crm.zetom.tests.test_duplicate_matcher -v 2`
Expected: FAIL — тесты `test_same_nip*`/`test_nip_only*` не находят кандидата (сейчас матчер читает `Client.company_nip`, у тестовых Client он не заполнен; NIP лежит на привязанной Company).

- [ ] **Step 3: Переписать `_candidate_queryset` (NIP/company через связь)**

В `crm/zetom/services/duplicate_matcher.py` заменить функцию `_candidate_queryset` целиком на:
```python
# claude — prefilter теперь тянет по NIP/названию ПРИВЯЗАННОЙ фирмы
# (Client.company_links → Company), а не по Client.company_*.
def _candidate_queryset(rn) -> "models.QuerySet[Client]":
    phone = _phone_str(rn.phone)
    email = _norm(rn.email)
    domain = _email_domain(rn.email)
    company = _norm(rn.company_name)
    nip = _norm(getattr(rn, "company_nip", None))
    last_name = _norm(rn.last_name)

    q = Q()
    if phone:
        q |= Q(phone=phone)
    if email:
        q |= Q(email__iexact=email)
    if domain:
        q |= Q(email__iendswith=f"@{domain}")
    if company:
        q |= Q(company_links__company__name__icontains=company)
    if nip:
        q |= Q(company_links__company__nip=nip)
    if last_name:
        q |= Q(last_name__iexact=last_name)
    if not q:
        return Client.objects.none()
    return (
        Client.objects.filter(q)
        .prefetch_related("company_links__company")
        .distinct()
    )
```

- [ ] **Step 4: Переписать NIP/company блоки в `_score_one`**

В `_score_one` заменить два блока (NIP и company). Найти:
```python
    rn_nip = _norm(getattr(rn, "company_nip", None))
    cl_nip = _norm(client.company_nip)
    if rn_nip and cl_nip and rn_nip == cl_nip:
        score += 50
        badges.append(Badge.of(BADGE_SAME_NIP))
        highlights["company_nip"] = client.company_nip or ""

    rn_company = _norm(rn.company_name)
    cl_company = _norm(client.company_name)
    if rn_company and cl_company and rn_company == cl_company:
        score += 20
        badges.append(Badge.of(BADGE_SAME_COMPANY))
        highlights["company_name"] = client.company_name or ""
```
и заменить на:
```python
    # claude — сигналы фирмы берём из ПРИВЯЗАННЫХ Company (человек может быть
    # в нескольких фирмах → совпадение по любой). company_links prefetch'ится.
    companies = [pl.company for pl in client.company_links.all()]
    cl_nips = {_norm(c.nip) for c in companies if c.nip}
    cl_names = {_norm(c.name) for c in companies if c.name}

    rn_nip = _norm(getattr(rn, "company_nip", None))
    if rn_nip and rn_nip in cl_nips:
        score += 50
        badges.append(Badge.of(BADGE_SAME_NIP))
        highlights["company_nip"] = rn_nip

    rn_company = _norm(rn.company_name)
    if rn_company and rn_company in cl_names:
        score += 20
        badges.append(Badge.of(BADGE_SAME_COMPANY))
        highlights["company_name"] = next(
            (c.name for c in companies if _norm(c.name) == rn_company), ""
        )
```
Остальные блоки (`phone`, `email`, `similar name`, `domain`) — БЕЗ изменений (читают поля `Client` напрямую). Проверить что переменные `rn_email`/`cl_email` для domain-блока по-прежнему определены выше (они есть).

- [ ] **Step 5: Прогнать новый тест + существующие VW-тесты**

Run:
```bash
python manage.py test crm.zetom.tests.test_duplicate_matcher -v 2
python manage.py test crm.zetom.tests.test_dupe_render_smoke -v 2
```
Expected: оба PASS (4 новых + smoke). Если smoke создаёт Client с `company_nip` и ждёт матч — обновить его фикстуры на Company+link (тот же паттерн `_person_in_company`); если smoke только про рендер — пройдёт как есть.

- [ ] **Step 6: Коммит**

```bash
git add crm/zetom/services/duplicate_matcher.py crm/zetom/tests/test_duplicate_matcher.py
git commit -m "refactor(zetom): VW dedup reads NIP/company from linked Company (phase 2a)"
```

---

### Task 2: Company-aware `ClientSearchView` + `client_autofill`

**Files:**
- Modify: `crm/clients/views.py` (`ClientSearchView.get`, `client_autofill`)
- Test: `crm/clients/tests/test_views.py` (переписать `ClientAutofillTests` — сейчас 2 теста падают из-за отсутствия `request.user`; заодно перевести на Company-источник)

**Interfaces:**
- Consumes: `Company` (`nip`/`name`/`comments`), `Client.company_links`.
- Produces:
  - `ClientSearchView` ищет `Client` по имени + по названию/NIP привязанной `Company`; в результатах `label`/`company_nip` берутся из привязанной фирмы.
  - `client_autofill` резолвит `Company` по `nip`, возвращает данные фирмы + первого привязанного человека.

- [ ] **Step 1: Переписать `ClientAutofillTests` под Company-источник + request.user**

Заменить `crm/clients/tests/test_views.py` целиком на:
```python
# claude
from django.contrib.auth.models import User
from django.test import TestCase
from django.test.client import RequestFactory

from crm.clients.models import Client, Company, CompanyPersonLink
from crm.clients.views import ClientSearchView, client_autofill


class ClientAutofillTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        # superuser: user_has_perm пропускает суперюзера на все коды
        self.user = User.objects.create_superuser(
            "staff", "staff@zetom.pl", "pass12345"
        )
        self.person = Client.objects.create(
            first_name="Sigma", last_name="Balls",
            email="email@gmail.com", phone="+48574358039",
        )
        self.company = Company.objects.create(
            name="Sigma Company", nip="5262706346", comments="sigma addr",
        )
        CompanyPersonLink.objects.create(company=self.company, person=self.person)

    def test_search_view_matches_company_name(self):
        request = self.factory.get("/clients/search/", {"q": "Sigma Company"})
        request.user = self.user
        response = ClientSearchView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["results"])
        self.assertEqual(data["results"][0]["id"], self.person.id)

    def test_client_autofill_by_nip(self):
        request = self.factory.get("/clients/autofill/", {"nip": "5262706346"})
        request.user = self.user
        response = client_autofill(request)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["exists"])
        self.assertEqual(data["company_name"], "Sigma Company")
        self.assertEqual(data["company_nip"], "5262706346")

    def test_autofill_unknown_nip(self):
        request = self.factory.get("/clients/autofill/", {"nip": "0000000000"})
        request.user = self.user
        response = client_autofill(request)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["exists"])
```

- [ ] **Step 2: Прогнать — падает**

Run: `python manage.py test crm.clients.tests.test_views -v 2`
Expected: FAIL — `test_search_view_matches_company_name` (search не матчит по Company) и/или `test_client_autofill_by_nip` (autofill ищет `Client.objects.get(company_nip=...)`, у person NIP нет).

- [ ] **Step 3: Переписать `ClientSearchView.get`**

В `crm/clients/views.py` заменить тело `ClientSearchView.get` (блок построения `query` и `clients`, и сериализацию) на Company-aware. Найти цикл, строящий `query` по `company_name`/`company_nip`/`first_name`/`last_name`, и `clients = Client.objects.filter(query)...`, плюс формирование `results`. Заменить на:
```python
        query = Q()
        for term in set(query_terms):
            query |= Q(first_name__icontains=term)
            query |= Q(last_name__icontains=term)
            query |= Q(company_links__company__name__icontains=term)
            query |= Q(company_links__company__nip__icontains=term)

        clients = (
            Client.objects.filter(query)
            .prefetch_related("company_links__company")
            .distinct()
            .order_by("last_name")[:20]
        )

        def _company_of(c):
            link = c.company_links.first()
            return link.company if link else None

        results = []
        for c in clients:
            company = _company_of(c)
            label = (
                (company.name if company else None)
                or f"{c.first_name or ''} {c.last_name or ''}".strip()
                or f"Client #{c.id}"
            )
            results.append({
                "id": c.id,
                "label": label,
                "email": c.email,
                "phone": c.phone.as_international if c.phone else "",
                "company_nip": company.nip if company else "",
                "address": company.comments if company else "",
            })
        return JsonResponse({"results": results})
```
(Оставить верхнюю часть метода — permission-гейт, разбор `q`/`query_terms` — без изменений.)

- [ ] **Step 4: Переписать `client_autofill`**

В `crm/clients/views.py` заменить тело `client_autofill` (после permission-гейта и проверки `nip`) на:
```python
    # claude — autofill теперь резолвит Company по NIP (NIP уехал с Client на
    # Company), + подтягивает первого привязанного человека.
    company = Company.objects.filter(nip=nip).first()
    if company is None:
        return JsonResponse({"exists": False})
    link = company.person_links.first()
    person = link.person if link else None
    return JsonResponse({
        "exists": True,
        "first_name": person.first_name if person else "",
        "last_name": person.last_name if person else "",
        "company_name": company.name,
        "company_nip": company.nip,
        "email": (person.email if person else "") or "",
        "phone": person.phone.as_international if (person and person.phone) else "",
        "address": company.comments or "",
    })
```
Добавить импорт `Company` вверху файла: изменить `from crm.clients.models import Client` на `from crm.clients.models import Client, Company`.

- [ ] **Step 5: Прогнать тесты**

Run: `python manage.py test crm.clients.tests.test_views -v 2`
Expected: PASS (3 теста).

- [ ] **Step 6: Коммит**

```bash
git add crm/clients/views.py crm/clients/tests/test_views.py
git commit -m "refactor(clients): Company-aware search + autofill-by-NIP (phase 2a)"
```

---

### Task 3: Верификация под-этапа 2a

- [ ] **Step 1: Прогнать всю затронутую поверхность**

Run:
```bash
python manage.py test crm.clients crm.zetom -v 1
```
Expected: PASS, КРОМЕ 1 известного pre-existing фейла `crm.zetom.tests.test_admin.ApproveNullAdminActionTests.test_approve_creates_main_sends_notification_and_redirects` (stale mock.patch, вне скоупа 2a). Два прежних `ClientAutofillTests` фейла теперь ПОЧИНЕНЫ (Task 3). Итог: `FAILED (errors=1)` с этим одним именем — новых фейлов нет.

- [ ] **Step 2: Проверка миграций**

Run: `python manage.py makemigrations --check --dry-run`
Expected: `No changes detected` (2a — только код, без изменения моделей).

- [ ] **Step 3: Смоук VW вручную (опц., если есть данные)**

Поднять сервер, открыть Validation Window по любому `RequestNull` с NIP, совпадающим с забэкфилленной `Company` → кандидат с бейджем «same NIP» должен появиться.

---

## Self-Review

**Spec coverage (2a):**
- Company-aware VW-дедуп (`duplicate_matcher`) → Task 1 ✅
- Company-aware search/autofill (`views.py`) → Task 2 ✅
- Rename НЕ делается (класс `Client` сохранён) ✅
- Поля `company_*`/`client_type` НЕ удаляются (fallback остаётся; удаление = 2c) ✅
- Починка 2 из 3 pre-existing фейлов (`ClientAutofillTests`) как побочный эффект Task 2 ✅

**Вне 2a:** интейк create/link + `ClientForm` + `ClientAdmin` сегмент (2b); удаление полей + очистка + UI-лейбл (2c); поверхности #11/#12 (Phase 3). Хелпер «фирмы человека» вводится в Phase 3, когда карточкам понадобится (в 2a не нужен — консьюмеры используют прямой `company_links` под prefetch).

**Placeholder scan:** код полный в каждом шаге; команды с ожидаемым выводом. Единственное «если» — smoke-тест `test_dupe_render_smoke` (Task 1 Step 5): инструкция явная (обновить фикстуры на Company+link ИЛИ пройдёт как есть) — исполнитель проверяет фактическим прогоном.

**Type consistency:** `company_links`/`person_links`/`Company.nip`/`Company.name`/`Company.comments` — имена из Phase 1, согласованы между Task 1/2 и тестами. `find_candidates`/`Badge`/`BADGE_*` — публичная сигнатура матчера не менялась.

## Риски / точки внимания

- **`duplicate_matcher` без исходного теста** — Task 1 Step 1 добавляет его ДО правки (TDD-страховка), включая кейс «NIP-only prefilter».
- **`test_dupe_render_smoke`** может требовать обновления фикстур (Company+link) — см. Task 1 Step 5.
- **1 pre-existing фейл остаётся** (`test_approve_...`, stale mock.patch) — вне скоупа; чинится отдельно.
- **Prefetch-инвариант:** и матчер, и search полагаются на `prefetch_related("company_links__company")` — держать его при любой правке queryset, иначе N+1.
