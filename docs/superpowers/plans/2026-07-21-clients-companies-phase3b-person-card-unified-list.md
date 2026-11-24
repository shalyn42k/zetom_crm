# Clients/Companies — Phase 3b (Person card + unified Klienci list) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Карточка человека (Osoba) с панелью «Firmy» + единый список «Klienci» (фирмы + частные лица), по дизайну handoff. Дополняет карточку фирмы (Phase 3a). Реализует хвост #11 (карточка человека) и #12 (единая база).

**Architecture:** По образцу Phase 3a. Карточка человека — кастомный `ClientAdmin.change_view` (уже есть кастомный, переписываем на новый дизайн: Dane osobowe + Firmy + Powiązane zgłoszenia + Historia). Единый список — кастомный `ClientAdmin.changelist_view`, рендерящий объединённую таблицу `Company` + «частные лица» (`Client` с 0 связей `company_links`) с фильтрами Rodzaj/Typ dostawcy/Szukaj и роутингом: строка-фирма → карточка Company (3a), строка-человек → карточка Osoba. Переиспользуем `static/clients/css/company_card.css` (+ доп. стили списка). Company-данные человека берём из `client.company_links` (не из `Client.company_*`). Additive: модели не меняются; `requestmain.py` inline-редактор и удаление полей — 3c/2c.

**Tech Stack:** Django 5.2 admin + Unfold, кастомные шаблоны + CSS, theme-aware `html.dark`, PL через `{% trans %}`, тесты `manage.py test`.

## Global Constraints

- Django 5.2 / Postgres. Тесты: `python manage.py test <path> -v 2` (`--keepdb` при leftover test-DB).
- Python-блоки Claude — `# claude`. **НЕ добавлять** `Co-Authored-By: Claude` (проверять сообщение).
- Многострочные комментарии в шаблонах — `{% comment %}…{% endcomment %}`, НЕ многострочный `{# #}`.
- Лейблы PL через `{% trans %}`; i18n-конвенция как в 3a — для доменных польских строк `msgstr`(pl)=`msgstr`(en)=идентичный польский литерал (экран польскоязычный независимо от locale). Перед завершением — makemessages→заполнить→compilemessages.
- Theme-aware через `html.dark` (не `data-theme`); переиспользовать токены из `static/clients/css/company_card.css`.
- Дизайн-эталон: `design_handoff_clients_unified/README.md` §«1. Klienci» + §«3. Karta osoby» + файл `Zetom Klienci.html`.
- Company-данные человека — только из `client.company_links[].company`. Не читать/писать `Client.company_*` (мертвы; дроп в 2c).
- RBAC как у `ClientAdmin`: `view_clients`/`edit_clients` через `user_has_perm`.
- «Частное лицо» = `Client` без единой связи `company_links`. «Контактное лицо фирмы» = `Client` со связью (в списке Osoby показываем всех Client; фильтр Rodzaj разделяет).

## Data contracts

**Карточка человека (change_view):**
```
osoba: Client
dane_osobowe: {imie, nazwisko, telefon, email}
firmy: [ {company_pk, nazwa, stanowisko, glowny, url=admin:clients_company_change} ]   # client.company_links → company + position/is_primary
zgloszenia: [ {label, data, dept, status_label, url} ]   # заявки человека (RequestClientLink); переиспользовать build_request_rows/get_client_request_summary
historia: [ {data, kanal_label, sotrudnik, kontakt_osoba, summary} ]   # ClientInteraction.filter(client=osoba)
can_edit
```

**Единый список (changelist_view):**
```
rows: [
  {kind:"company", pk, nazwa, nip, typ_label, telefon, email, zgloszenia_count, url=company_change}
  {kind:"person",  pk, nazwa=imie+nazwisko, nip="—", typ_label="Osoba prywatna", telefon, email, zgloszenia_count, url=client_change}
]
counts: {all, firmy, osoby}
current_rodzaj: "" | "firmy" | "osoby"
type_supplier_choices, q
```

---

### Task 1: Карточка человека (`ClientAdmin.change_view` → новый дизайн)

**Files:**
- Modify: `crm/clients/admin.py` (`ClientAdmin.change_view` + контекст-билдер; person-edit endpoint в `get_urls`)
- Create: `crm/clients/templates/admin/clients/client/person_card.html` (новый шаблон; старый `change_form.html` пока оставить, переключим `change_form_template`)
- Modify: `static/clients/css/company_card.css` (доп. стили карточки человека, если нужны — переиспользовать панели)
- Test: `crm/clients/tests/test_person_card.py`

**Interfaces:**
- Consumes: `Client`, `client.company_links` → `Company`, `ClientInteraction`, `build_request_rows`/`get_client_request_summary` (`crm/clients/services.py`).
- Produces: `GET /admin/clients/client/<pk>/change/` рендерит карточку Osoba (Dane osobowe + Firmy + Powiązane zgłoszenia + Historia); `POST client/<pk>/person/save/` (name `clients_client_person_save`, RBAC edit_clients) обновляет person-поля (imie/nazwisko/telefon/email).

- [ ] **Step 1: Падающий тест**

Create `crm/clients/tests/test_person_card.py`:
```python
# claude
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from crm.clients.models import Client, Company, CompanyPersonLink


class PersonCardTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("staff", "s@s.pl", "pass12345")
        self.client.force_login(self.user)

    def test_card_shows_person_and_firmy(self):
        person = Client.objects.create(first_name="Jan", last_name="Kowalski", email="j@z.pl")
        company = Company.objects.create(name="Zetom", nip="1234563218")
        CompanyPersonLink.objects.create(company=company, person=person, position="Kierownik")
        resp = self.client.get(reverse("admin:clients_client_change", args=[person.pk]), HTTP_HOST="127.0.0.1")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Jan")
        self.assertContains(resp, "Dane osobowe")
        self.assertContains(resp, "Firmy")
        self.assertContains(resp, "Zetom")
        self.assertContains(resp, "Kierownik")

    def test_person_save_updates_fields(self):
        person = Client.objects.create(first_name="Old")
        url = reverse("admin:clients_client_person_save", args=[person.pk])
        resp = self.client.post(url, {"first_name": "New", "last_name": "Name", "email": "n@n.pl"}, HTTP_HOST="127.0.0.1")
        self.assertTrue(resp.json()["ok"])
        person.refresh_from_db()
        self.assertEqual(person.first_name, "New")
```

- [ ] **Step 2: Прогнать — падает** (старый change_form не содержит «Dane osobowe»/«Firmy»; save-endpoint нет).

Run: `python manage.py test crm.clients.tests.test_person_card -v 2`

- [ ] **Step 3: Переписать `ClientAdmin.change_view` + контекст** под data-contract (см. выше), `change_form_template = "admin/clients/client/person_card.html"`. Firmy из `client.company_links.all()` (prefetch), заявки через существующий `build_request_rows`/`get_client_request_summary`, история `ClientInteraction.filter(client=osoba)`. Добавить `person_save` endpoint в `get_urls` (RBAC edit_clients, `# claude`).

- [ ] **Step 4: Создать шаблон `person_card.html`** — backrow «Wróć» + «Osoba · podgląd»; id-hero (person, синий); панели **Dane osobowe** (Imię/Nazwisko/Telefon/E-mail + карандаш→модалка mOsobowe→save endpoint), **Firmy** (таблица Firma|Stanowisko, строки кликабельны→карточка фирмы, звезда=Główny), **Powiązane zgłoszenia**, **Historia kontaktów** (read-only + nota). Переиспользовать классы/токены `company_card.css`. Лейблы `{% trans %}`.

- [ ] **Step 5: Прогнать тест** → PASS. `python manage.py check`.

- [ ] **Step 6: Коммит** `feat(clients): custom Person (Osoba) detail card + Firmy panel (phase 3b)`.

---

### Task 2: Единый список «Klienci» (`ClientAdmin.changelist_view` → фирмы + частные лица)

**Files:**
- Modify: `crm/clients/admin.py` (`ClientAdmin.changelist_view` + `change_list_template`)
- Create: `crm/clients/templates/admin/clients/client/klienci_list.html`
- Modify: `static/clients/css/company_card.css` (стили списка/таблицы/сегмента/пейджера)
- Test: `crm/clients/tests/test_klienci_list.py`

**Interfaces:**
- Consumes: `Company`, `Client` (частные = без `company_links`), `RequestMain.company` (счётчик заявок фирмы), `RequestClientLink` (счётчик заявок человека).
- Produces: `GET /admin/clients/client/` рендерит единый список = фирмы + частные лица; фильтры `?rodzaj=firmy|osoby`, `?typ=<supplier>`, `?q=<search>`; строки роутят на карточку фирмы/человека.

- [ ] **Step 1: Падающий тест**

Create `crm/clients/tests/test_klienci_list.py`:
```python
# claude
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from crm.clients.models import Client, Company, CompanyPersonLink


class KlienciListTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("staff", "s@s.pl", "pass12345")
        self.client.force_login(self.user)
        self.firma = Company.objects.create(name="Zetom Sp.", nip="1234563218")
        self.osoba = Client.objects.create(first_name="Jan", last_name="Prywatny")  # no links = private
        linked = Client.objects.create(first_name="Anna", last_name="Kontakt")
        CompanyPersonLink.objects.create(company=self.firma, person=linked)  # contact, not private

    def _get(self, **params):
        return self.client.get(reverse("admin:clients_client_changelist"), params, HTTP_HOST="127.0.0.1")

    def test_list_shows_company_and_private_person(self):
        resp = self._get()
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Zetom Sp.")       # firma
        self.assertContains(resp, "Jan Prywatny")     # private person
        self.assertContains(resp, "Osoba prywatna")

    def test_filter_firmy_only(self):
        resp = self._get(rodzaj="firmy")
        self.assertContains(resp, "Zetom Sp.")
        self.assertNotContains(resp, "Jan Prywatny")

    def test_filter_osoby_only(self):
        resp = self._get(rodzaj="osoby")
        self.assertContains(resp, "Jan Prywatny")
        self.assertNotContains(resp, "Zetom Sp.")
```

- [ ] **Step 2: Прогнать — падает** (старый список сегментирован по `client_type`, не показывает Company; нет «Osoba prywatna»).

Run: `python manage.py test crm.clients.tests.test_klienci_list -v 2`

- [ ] **Step 3: Переписать `ClientAdmin.changelist_view`** — собрать `rows` = Companies + Clients-без-`company_links` по data-contract; применить `rodzaj`/`typ`/`q` фильтры на уровне сборки; посчитать `counts`; простая пагинация (срез/`Paginator` по объединённому списку). `change_list_template = "admin/clients/client/klienci_list.html"`. `# claude`. Роутинг URL: фирма→`admin:clients_company_change`, человек→`admin:clients_client_change`.

- [ ] **Step 4: Создать шаблон `klienci_list.html`** — page header «Klienci» + кнопка «Dodaj klienta»; toolbar (сегмент Rodzaj Wszyscy/Firmy/Osoby со счётчиками · select Typ dostawcy · поиск Szukaj); таблица в `.tbl-scroll` (min-width) колонки `Nazwa/Imię | NIP | Typ | Telefon | E-mail | Zgłoszenia`; строки кликабельны (аватар person=синий/company=фиолетовый, pill Firma/Osoba, badge Zgłoszenia); footer «Pokazano … z … klientów» + пейджер. Дизайн §1 handoff. Лейблы `{% trans %}`.

- [ ] **Step 5: Прогнать тест** → PASS. `python manage.py check`.

- [ ] **Step 6: Коммит** `feat(clients): unified Klienci list (companies + private persons) (phase 3b)`.

---

### Task 3: i18n + верификация 3b

- [ ] **Step 1:** `makemessages -l pl -l en` → заполнить новые card/list-строки (PL=EN identity для доменных, как в 3a). `compilemessages`.
- [ ] **Step 2:** `python manage.py test crm.clients crm.zetom --noinput` → PASS кроме 1 известного pre-existing (`test_approve_...`). Проверить что старые Client-тесты (`tests/test_views.py`, `test_admin`) не сломаны переездом change_view/changelist.
- [ ] **Step 3:** `makemigrations --check --dry-run` → «No changes detected».
- [ ] **Step 4:** Смоук: `/admin/clients/client/` (единый список, фильтры Rodzaj), клик по фирме → карточка фирмы, клик по частному лицу → карточка человека; дарк-тема. Коммит переводов.

---

## Self-Review

**Spec coverage (Phase 3b):**
- Карточка человека + панель Firmy → Task 1 ✅
- Единый список «Klienci» (фирмы + частные лица) + фильтры → Task 2 ✅
- i18n + верификация → Task 3 ✅
- Company-данные из связей (не `Client.company_*`) ✅; модели не меняются ✅

**Вне 3b:** inline-client-редактор на RequestMain (`requestmain.py` create/edit/save_client_json) + его старые Client-шаблоны — 3c; дроп полей `company_*`/`client_type` + `ClientForm`/`ClientAdmin` company-поля — 2c. Кнопка «привязать существующего человека к ещё одной фирме» (multi-company UI) — отдельный минорный пункт, можно в 3c/после.

**Placeholder scan:** data-contracts, эндпоинты, тесты, дизайн-эталон заданы; объёмная верстка делегируется исполнителю с `design_handoff_clients_unified/` — спецификация, не плейсхолдер.

**Type consistency:** контекст-ключи (`osoba`/`dane_osobowe`/`firmy`/`zgloszenia`/`historia`; `rows`/`counts`/`current_rodzaj`) согласованы между change_view/changelist_view (Task 1/2) и шаблонами. Эндпоинт `clients_client_person_save` — между get_urls и тестом. `company_links`/`RequestMain.company`/`RequestClientLink` — имена из Phase 1/2.

## Риски / точки внимания

- **Замена `changelist_view`/`change_view`** — старые кастомные шаблоны `client/change_form.html`+`change_list.html` перестают использоваться (переключаем `*_template`). Проверить что старые тесты (`test_views`, `test_admin`) не завязаны на старый рендер; если завязаны — обновить.
- **Пагинация объединённого списка** (Company+Client) — не QuerySet, а список; использовать `django.core.paginator.Paginator` по собранному списку.
- **Company-данные человека из `company_links`** — держать prefetch, чтобы карточка/список не давали N+1 (см. урок 2a: `.first()` на prefetch-менеджере → `.all()[0]`).
- **1 pre-existing фейл** (`test_approve_...`) остаётся — вне скоупа.
- Каждый таск-коммит держит дерево зелёным (additive-переключение шаблонов) — безопасно прерваться между тасками.
