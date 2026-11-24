# Clients/Companies — Phase 3a (Company detail card) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Кастомная страница-карточка фирмы (Unfold admin `Company` change view) по дизайну handoff: панели Dane podstawowe / Dane szczegółowe / Osoby kontaktowe (+ добавление) / Powiązane zgłoszenia / Historia kontaktów. Реализует требование **#11**.

**Architecture:** Даём `CompanyAdmin` (из Phase 1) кастомный `change_view`, который рендерит свой шаблон с контекстом (по образцу `ClientAdmin.change_view` в `crm/clients/admin.py` — тот же паттерн: собрать контекст → `render(request, template, context)`, эндпоинты через `get_urls`+`admin_view`). Осoby kontaktowe редактируются 3 JSON-эндпоинтами (add/edit/delete person-contact), как inline-редактор в `requestmain.py`. Всё additive: существующий `CompanyAdmin`/`Client`/заявки не ломаются. Дизайн-эталон — `design_handoff_clients_unified/` (README.md + `Zetom Klienci.html`, экран «Karta firmy»).

**Tech Stack:** Django 5.2 admin + Unfold, кастомный шаблон + CSS (токены из handoff), theme-aware через `html.dark`, PL-лейблы через `{% trans %}`, тесты `manage.py test`.

## Global Constraints

- Django 5.2 / Postgres. Тесты: `python manage.py test <path> -v 2` (`--keepdb` при leftover test-DB).
- Python-блоки Claude помечать `# claude`. **НЕ добавлять** `Co-Authored-By: Claude` (проверять сообщение перед коммитом).
- Лейблы UI — польские через `{% trans %}` / `gettext_lazy`. Словарь (verbatim из handoff README): Klient/Firma, Osoby kontaktowe, Dodaj osobę kontaktową, Stanowisko, Główny kontakt, Dane podstawowe, Dane szczegółowe, Powiązane zgłoszenia, Historia kontaktów, Wróć, Typ dostawcy, Kraj, Miasto, Województwo, Kod pocztowy, Ulica, Telefon, E-mail, NIP, REGON, Nazwa, Operacje, Edytuj, Usuń, Anuluj, Zapisz. Перед завершением 3a — makemessages→PL+EN→compilemessages.
- **Theme-aware:** дарк ловить через `html.dark` (Unfold ставит `class="dark"` на `<html>`, НЕ `data-theme`). Токены определить дважды: `:root` (светлая) и `html.dark` (тёмная). Значения токенов — из handoff README «Design Tokens» (скопировать оба набора verbatim).
- **Дизайн-эталон:** `design_handoff_clients_unified/README.md` §«2. Karta firmy» + файл `Zetom Klienci.html` (экран Firma) — воспроизвести раскладку/панели/классы средствами Unfold-шаблона. Прототип = референс, не копипаст; инлайнить SVG-иконки как в прототипе.
- RBAC: гейты как у `CompanyAdmin` (Phase 1) — `view_clients`/`edit_clients` через `crm.users.utils.user_has_perm`.
- Не трогать `Client`, `RequestMain`, интейк — 3a только про Company-карточку.

## Data contract (контекст шаблона, собирается в change_view)

```
company: Company
panels:
  dane_podstawowe: {nazwa, nip, regon, typ_label}          # typ_label = get_type_supplier_display
  dane_szczegolowe: {kraj, miasto, wojewodztwo, kod, ulica, email, telefon}
osoby: [ {pk, imie, nazwisko, email, telefon, stanowisko, glowny(bool)} ]   # из company.person_links → link.person + link.position/is_primary
zgloszenia: [ {label, data, dept, status_label, url} ]     # RequestMain.objects.filter(company=company)
historia: [ {data, kanal_label, sotrudnik, kontakt_osoba, summary} ]  # ClientInteraction по людям фирмы (read-only)
can_edit: bool
```

---

### Task 1: Кастомный `change_view` фирмы + шаблон (панели Dane + CSS-токены)

**Files:**
- Modify: `crm/clients/admin.py` (`CompanyAdmin`: `change_view`, `change_form_template`, контекст-билдер)
- Create: `crm/clients/templates/admin/clients/company/change_form.html`
- Create: `static/clients/css/company_card.css`
- Test: `crm/clients/tests/test_company_card.py`

**Interfaces:**
- Consumes: `Company`, `CompanyPersonLink`, `crm.users.utils.user_has_perm`.
- Produces: `GET /admin/clients/company/<pk>/change/` рендерит кастоммную карточку (панели Dane podstawowe + Dane szczegółowe + пустые каркасы Osoby/Zgłoszenia/Historia), 200, дарк-тема через `html.dark`.

- [ ] **Step 1: Написать падающий тест (страница рендерится, показывает данные фирмы)**

Create `crm/clients/tests/test_company_card.py`:
```python
# claude
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class CompanyCardTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("staff", "s@s.pl", "pass12345")
        self.client.force_login(self.user)

    def test_card_renders_company_basics(self):
        from crm.clients.models import Company, SupplierType
        company = Company.objects.create(
            name="Zetom Sp. z o.o.", nip="1234563218", regon="123456785",
            type_supplier=SupplierType.REGIONAL, city="Katowice", email="biuro@zetom.pl",
        )
        url = reverse("admin:clients_company_change", args=[company.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Zetom Sp. z o.o.")
        self.assertContains(resp, "1234563218")
        self.assertContains(resp, "Dane podstawowe")
        self.assertContains(resp, "Osoby kontaktowe")
```

- [ ] **Step 2: Прогнать — падает**

Run: `python manage.py test crm.clients.tests.test_company_card -v 2`
Expected: FAIL — дефолтный admin change (нет «Dane podstawowe» текста / кастомного шаблона).

- [ ] **Step 3: Реализовать `change_view` + контекст-билдер в `CompanyAdmin`**

В `crm/clients/admin.py`, в `CompanyAdmin`, добавить `change_form_template = "admin/clients/company/change_form.html"` и метод `change_view`, собирающий data-contract (см. выше) и рендерящий шаблон. Паттерн — как `ClientAdmin.change_view` (тот же файл): проверить `has_view_permission`, собрать контекст (`**self.admin_site.each_context(request)`, `opts`, `company`, панели, списки), вернуть `render(request, self.change_form_template, context)`. В 3a `osoby`/`zgloszenia`/`historia` можно собрать реально (Task 3 их допилит визуально) — минимум для теста нужны панели Dane. Пометить блок `# claude`.

- [ ] **Step 4: Создать шаблон + CSS**

Create `crm/clients/templates/admin/clients/company/change_form.html`: extends Unfold admin base; backrow «Wróć» + «Klient / Firma»; id-hero (аватар+название+pill Firma+Typ+NIP); `.stack` с панелями `Dane podstawowe` (Nazwa/NIP/REGON/Typ) и `Dane szczegółowe` (Kraj/Miasto/Województwo/Kod/Ulica/E-mail/Telefon); каркасы панелей Osoby kontaktowe / Powiązane zgłoszenia / Historia kontaktów (наполняются в Task 2-3). Лейблы через `{% trans %}`. Подключить `{% load static %}` + `<link rel="stylesheet" href="{% static 'clients/css/company_card.css' %}">`.
Create `static/clients/css/company_card.css`: токены `:root` (light) + `html.dark` (dark) — **скопировать оба набора из handoff README «Design Tokens» verbatim**; стили панелей `.panel`/`.frow`/id-hero/backrow по раскладке handoff §2. Воспроизвести визуал прототипа `Zetom Klienci.html` (экран Firma).

- [ ] **Step 5: Прогнать тест + смоук**

Run: `python manage.py test crm.clients.tests.test_company_card -v 2` → PASS.
Run: `python manage.py check` → no issues.

- [ ] **Step 6: Коммит**

```bash
git add crm/clients/admin.py crm/clients/templates/admin/clients/company/ static/clients/css/company_card.css crm/clients/tests/test_company_card.py
git commit -m "feat(clients): custom Company detail card — Dane panels (phase 3a)"
```

---

### Task 2: Панель «Osoby kontaktowe» + add/edit/delete контакта

**Files:**
- Modify: `crm/clients/admin.py` (`CompanyAdmin.get_urls` + JSON-эндпоинты; контекст `osoby`)
- Modify: `crm/clients/templates/admin/clients/company/change_form.html` (таблица + модалка + JS)
- Modify: `static/clients/css/company_card.css` (стили таблицы/модалки/empty-state)
- Test: `crm/clients/tests/test_company_contacts.py`

**Interfaces:**
- Consumes: `Client` (person), `CompanyPersonLink`.
- Produces: эндпоинты (под `admin_view`, RBAC `edit_clients`):
  - `POST company/<pk>/person/add/` — создать `Client`(person) + `CompanyPersonLink(company, person, position, is_primary)`; вернуть JSON строки.
  - `POST company/<pk>/person/<link_pk>/edit/` — обновить person + link.
  - `POST company/<pk>/person/<link_pk>/delete/` — удалить `CompanyPersonLink` (person не трогаем).

- [ ] **Step 1: Написать падающий тест эндпоинтов**

Create `crm/clients/tests/test_company_contacts.py`:
```python
# claude
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from crm.clients.models import Client, Company, CompanyPersonLink


class CompanyContactsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("staff", "s@s.pl", "pass12345")
        self.client.force_login(self.user)
        self.company = Company.objects.create(name="Zetom", nip="1234563218")

    def test_add_contact_creates_person_and_link(self):
        url = reverse("admin:clients_company_person_add", args=[self.company.pk])
        resp = self.client.post(url, {
            "first_name": "Jan", "last_name": "Kowalski",
            "email": "j@z.pl", "phone": "+48501600300",
            "position": "Kierownik", "is_primary": "1",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        link = CompanyPersonLink.objects.get(company=self.company)
        self.assertEqual(link.person.first_name, "Jan")
        self.assertEqual(link.position, "Kierownik")
        self.assertTrue(link.is_primary)

    def test_delete_contact_removes_link_keeps_person(self):
        person = Client.objects.create(first_name="Jan")
        link = CompanyPersonLink.objects.create(company=self.company, person=person)
        url = reverse("admin:clients_company_person_delete", args=[self.company.pk, link.pk])
        resp = self.client.post(url)
        self.assertTrue(resp.json()["ok"])
        self.assertFalse(CompanyPersonLink.objects.filter(pk=link.pk).exists())
        self.assertTrue(Client.objects.filter(pk=person.pk).exists())  # person kept
```

- [ ] **Step 2: Прогнать — падает** (`NoReverseMatch` — эндпоинтов нет).

Run: `python manage.py test crm.clients.tests.test_company_contacts -v 2`

- [ ] **Step 3: Добавить эндпоинты в `CompanyAdmin.get_urls`** (имена `clients_company_person_add`/`_edit`/`_delete`), реализовать view-функции (RBAC `edit_clients`, `# claude`). add: создать Client(person-поля) + CompanyPersonLink; edit: обновить; delete: удалить link. Вернуть JSON со строкой контакта.

- [ ] **Step 4: Наполнить панель Osoby kontaktowe в шаблоне** — таблица `Imię|Nazwisko|E-mail|Telefon|Stanowisko|Operacje` (первый/`is_primary` со звёздочкой=Główny kontakt), кнопка «Dodaj osobę kontaktową» → модалка `mPerson` (Imię/Nazwisko/Telefon/E-mail/Stanowisko + чекбокс Główny kontakt), edit/delete иконки; пустое состояние = крупная «+ Dodaj osobę». JS дёргает эндпоинты, обновляет таблицу. Стили — из handoff.

- [ ] **Step 5: Прогнать тест** → PASS. `python manage.py check`.

- [ ] **Step 6: Коммит**

```bash
git add crm/clients/admin.py crm/clients/templates/admin/clients/company/ static/clients/css/company_card.css crm/clients/tests/test_company_contacts.py
git commit -m "feat(clients): Company card Osoby kontaktowe add/edit/delete (phase 3a)"
```

---

### Task 3: Панели «Powiązane zgłoszenia» + «Historia kontaktów» (real data)

**Files:**
- Modify: `crm/clients/admin.py` (контекст `zgloszenia` + `historia`)
- Modify: `crm/clients/templates/admin/clients/company/change_form.html`
- Test: `crm/clients/tests/test_company_card_panels.py`

**Interfaces:**
- Consumes: `RequestMain.objects.filter(company=...)`; `ClientInteraction` по людям фирмы (`client__company_links__company=company`).
- Produces: панель заявок (label/дата/отдел/статус, ссылка на change) + read-only таймлайн истории (дата · канал · сотрудник → контактное лицо · summary) с нотой «Tylko podgląd».

- [ ] **Step 1: Падающий тест** (в `test_company_card_panels.py`): создать Company + связанный RequestMain(company=…) + ClientInteraction по человеку фирмы; GET карточки; `assertContains` label заявки + текст истории + «Powiązane zgłoszenia» + «Historia kontaktów».
- [ ] **Step 2: Прогнать — падает.**
- [ ] **Step 3: Достроить контекст** `zgloszenia`/`historia` в `change_view` (см. data-contract; статус→PL-лейбл через реальный `RequestStatus`/`get_status_display`; канал→`get_channel_display`). `# claude`.
- [ ] **Step 4: Наполнить панели в шаблоне** (`.req` список заявок кликабельны; `.hev` таймлайн + `.readonly-note` «Tylko podgląd — dodawanie wpisów będzie dostępne później»). Обогатить строку истории: дата · канал · сотрудник → контактное лицо · заявка · summary (по фидбеку — показать канал/контактное лицо/заявку).
- [ ] **Step 5: Прогнать тест** → PASS.
- [ ] **Step 6: Коммит** `feat(clients): Company card requests + contact history panels (phase 3a)`.

---

### Task 4: i18n + верификация 3a

- [ ] **Step 1:** `python manage.py makemessages -l pl -l en` → перевести новые строки (словарь выше, PL) в обоих `.po`.
- [ ] **Step 2:** `python manage.py compilemessages`.
- [ ] **Step 3:** `python manage.py test crm.clients crm.zetom --noinput` → PASS кроме 1 известного pre-existing (`test_approve_...`).
- [ ] **Step 4:** `python manage.py makemigrations --check --dry-run` → «No changes detected» (3a без изменения моделей).
- [ ] **Step 5:** Смоук: поднять сервер, открыть `/admin/clients/company/<pk>/change/`, проверить панели + добавление контакта + дарк-тему (Unfold toggle). Коммит переводов.

---

## Self-Review

**Spec coverage (#11 / Phase 3a):**
- Карточка фирмы + Dane панели → Task 1 ✅
- Osoby kontaktowe + «+»/edit/delete → Task 2 ✅
- Powiązane zgłoszenia + Historia kontaktów (read-only, обогащённая) → Task 3 ✅
- i18n PL+EN, theme-aware `html.dark`, дизайн по handoff → Constraints + Task 4 ✅

**Вне 3a:** единый список «Klienci» + карточка человека (3b); миграция inline-client-редактора `requestmain.py` + Client-шаблонов на Company (3c, вместе с UI); field-drop `company_*` (2c, финал). Всё additive — существующий Client/request UI не трогается.

**Placeholder scan:** таск-код даёт data-contract, структуру панелей, имена эндпоинтов, тесты и точные токены-источник (handoff README verbatim). Объёмная верстка/CSS делегируется исполнителю с эталоном `design_handoff_clients_unified/` — это спецификация, не плейсхолдер.

**Type consistency:** контекст-ключи (`osoby`/`zgloszenia`/`historia`/панели) согласованы между change_view (Task 1/3) и шаблоном; эндпоинты `clients_company_person_add/edit/delete` — между `get_urls` (Task 2) и тестами. `company.person_links`/`RequestMain.company`/`ClientInteraction` — имена из Phase 1.

## Риски / точки внимания

- **Объём верстки** — самый большой таск. Исполнителю держать эталон `design_handoff_clients_unified/Zetom Klienci.html` (экран Firma) открытым; токены копировать verbatim.
- **`is_primary` порядок** — при выводе Osoby «первый=Główny» лучше сортировать `-is_primary` (учесть deferred-minor из 2a).
- **Дарк-тема** — `html.dark`, не `data-theme`; проверить оба режима.
- Каждый таск-коммит держит дерево зелёным (additive) — безопасно прерваться между тасками.
