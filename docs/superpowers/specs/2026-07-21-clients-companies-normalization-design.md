# Клиенты и фирмы: нормализация (Company + Person + M2M)

Дата: 2026-07-21
Скоуп-владелец: Тимур (модуль `clients` / `zetom`)
Пункты требований: **#10** (клиенты без фирмы + мульти-фирма), **#11** (экран фирмы: контактные лица + история), **#12** (единая база клиентов).

## 1. Проблема

Сейчас `crm/clients/models.py::Client` — это блоб «человек ИЛИ фирма» в одной таблице:
`company_name`/`company_nip` — просто текст-поля; `client_type` = PERSON/COMPANY — флаг.
Заявки (`RequestMain`/`Oferta`/`Zlecenie`/`Wniosek`) уже цепляются к `Client` через M2M
(`RequestClientLink` и т.д.), `ClientInteraction` — FK на один `Client`.

Требования заказчика ломают эту схему:
- клиент может быть частным лицом **без фирмы**;
- один человек может быть **в нескольких фирмах**;
- у фирмы — список **контактных лиц** с «+» и история контактов;
- единая **база клиентов** (фирмы + частные лица).

Legacy Zetbase (эталон UX) хранит всё embedded в один документ `Business` + копирует
клиента снапшотом в заявку. Ссылочной целостности нет, человек заперт в одной фирме,
канала контакта и напоминаний нет. **Наша цель — нормализовать то, что там денормализовано.**

## 2. Скоуп

**В этом заходе:**
- модель `Company` (фирма);
- **rename `Client`→`Person` ОТМЕНЁН** (решение 2026-07-21): класс остаётся `Client` (= теперь человек), UI-лейбл меняется на «Osoba» через `verbose_name`/i18n. Причина: rename = ~15 файлов чистого churn поверх обязательной Company-aware переписки, риск задеть свежий код (VW/client-pages/add-client);
- M2M `Company ↔ Client` через `CompanyPersonLink` (должность/роль);
- FK `RequestMain.company`; заявитель-люди остаются через существующий M2M;
- Company-aware переписка консьюмеров (VW-дедуп, search/autofill, интейк) — NIP/название фирмы берутся из `Company` через связь, а не из `Client.company_*`;
- удаление `company_name`/`company_nip`/`client_type` с `Client`;
- миграция данных: бэкфилл `Company` (Phase 1, готово), очистка company-only `Client`-строк;
- поверхности (Unfold admin): единый список «Klienci», карточка фирмы (Dane + Osoby kontaktowe + «+»),
  карточка человека; история контактов показывается **read-only** (существующий `ClientInteraction`).

**Паркуется (отдельная тема — «заметки и напоминания»):**
- `StepNote` (пункт 1, чужой модуль);
- write-флоу разговоров/`ContactLog`, канал контакта;
- «дата следующего контакта» → дедлайн/крон/уведомление (#7, чужой владелец);
- дашборд сотрудника (#13).
- филиалы `Oddziały`/`Filia` (Company проектируется так, чтобы `Branch(FK→Company)` доклеился позже; сейчас YAGNI).

## 3. Целевая data-model

```
Company                              [UI PL: «Klient» / «Firma»]
  name, short_name, full_name
  nip (normalize_nip), regon
  type_supplier: {lokalny|regionalny|miedzynarodowy}
  city, country, street, voivodeship, post_code
  phone, email, comments
  created_at

Person                               [UI PL: «Osoba kontaktowa»]  (бывший Client)
  first_name, last_name, phone, email
  notes, created_at
  (company_name / company_nip / client_type — УДАЛЯЮТСЯ, уезжают в Company/связь)

CompanyPersonLink  (through, M2M)     [UI PL: «Stanowisko»]
  company (FK), person (FK)
  position / role
  is_primary (bool, опц. — ЛПР/главный; в Zetbase нет, наша фича)
  linked_by (FK User), created_at

RequestMain
  + company (FK → Company, null=True)   — в какой фирме заявка
  clients (M2M → Person)                — заявитель(и); существующий RequestClientLink
  (дети Oferta/Zlecenie/Wniosek цепляются к своему RequestMain — без изменений)

ClientInteraction  (без изменений в этом заходе; только FK client → Person после rename)
```

Правила:
- «Клиент без фирмы» = `Person` с нулём связей `CompanyPersonLink`.
- «Человек в N фирмах» = несколько `CompanyPersonLink`.
- «Контактные лица фирмы» = `Person`, связанные с данной `Company`.
- Заявитель по заявке может отличаться от того, с кем реально идёт контакт (это уровень истории/нот — паркуется).

## 3.1. Search / autofill / intake — Company-aware (решение)

NIP и название фирмы уезжают с `Person` на `Company`. Все консьюмеры этих полей переписываются на Company (без денормализованного зеркала):
- **Поиск клиента** (`ClientSearchView`): матчит `Company`(name/nip) + `Person`(имя).
- **Autofill-по-NIP** (`client_autofill`): резолвит `Company` по NIP, префиллит фирменный блок.
- **VW-дедуп** (`duplicate_matcher._candidate_queryset`/`_score_one`): ранжирует кандидатов по `Company.nip`/`Company.name` (+ `Person` по имени/контактам); highlights бьют по Company-полям.
- **Интейк-создание** (`requestmain.py`, `requestnull_validate.py`, `admin/base.py`): при линке/создании выбирает/создаёт `Company` по NIP + опц. `Person`, вешает `RequestClientLink`(→Person) и `RequestMain.company`.
- Снапшот `company_name`/`company_nip` НА самой заявке (`RequestTemplate`) — **остаётся** (интейк-текст, как в Zetbase); autofill префиллит его из найденной `Company`.

## 3.2. Blast radius (уточнённый, честный)

Не «механический rename». Затрагивает недавно доделанное:
- `crm/clients/`: models, forms(`ClientForm`), fields(`ClientField`), views(search/autofill/attach/detach/suggest/create), admin(`ClientAdmin` List/Detail + сегмент `client_type`, `ClientInteractionInline`/`Admin`), services, urls, tests.
- `crm/zetom/`: `services/duplicate_matcher.py` (VW-дедуп), `admin/requestnull_validate.py` (VW-форма), `admin/requestmain.py` (create/link на save), `admin/base.py` («Create new» prefill), 4 through-модели (`*ClientLink` → авто-follow rename), tests.
- Не затрагивает: `notification` (читает `parent.company_name` заявки), request-снапшот-поля.

## 3.3. Фазировка (каждая фаза — рабочий, тестируемый софт)

- **Фаза 1 — фундамент (additive, ничего не ломает):** модели `Company` + `CompanyPersonLink`; `RequestMain.company` (nullable); admin-регистрация Company + inline; data-migration бэкфилла из существующих `Client.company_*`. `Client` пока не трогаем — дуальное состояние, всё работает.
- **Фаза 2 — Company-aware консьюмеры + удаление company_* (БЕЗ rename).** Дробится:
  - **2a** — Company-aware read-слой: хелпер «фирмы человека» на `Client`; переписать VW-дедуп (`duplicate_matcher`) и search/autofill (`views.py`) читать NIP/название из `Company` через связь (company_* ещё существуют как fallback, тесты зелёные).
  - **2b** — интейк create/link (`requestnull_validate._do_approve`, `requestmain.response_add`, `admin/base.py` prefill) через общий хелпер `create_person_with_company`: создавать/находить `Company` по NIP + `Client`(person) + связь, ставить `RequestMain.company`; перестать писать `company_*` на `Client`.
  - **2c** — `ClientForm` без company-полей + `ClientAdmin` без сегмента `client_type`/колонок company + миграция очистки company-only строк + удалить `company_name`/`company_nip`/`client_type` с `Client` + UI-лейбл `Client`→«Osoba» + i18n. (ClientForm/ClientAdmin здесь, а не в 2b: они связаны с существованием полей и с Phase-3 переверсткой List.)
- **Фаза 3 — поверхности #11/#12:** единый список «Klienci», карточки фирмы/человека, блок «Osoby kontaktowe» + «+» — по выходу дизайн-агента.

Планы пишутся по фазам: Фаза 1 (готово); Фаза 2 по под-этапам 2a→2b→2c; Фаза 3 — после дизайн-агента.

## 4. Стратегия миграции данных

1. Создать `Company`, `CompanyPersonLink` (пустые).
2. Переименовать модель `Client` → `Person` (`RenameModel`); through-таблицы (`*ClientLink`)
   FK-строки `"clients.Client"` обновляются автоматически.
3. Data-migration: для каждого существующего `Person` с непустым `company_name`:
   - найти/создать `Company` по нормализованному `nip` (или по имени, если nip пуст);
   - создать `CompanyPersonLink(company, person)`;
   - у заявок, где этот person привязан, проставить `RequestMain.company`.
4. Удалить поля `company_name`, `company_nip`, `client_type` с `Person`.

Порядок зетом-миграций: следующая нумеруется от `0013` (0011/0012 заняты StepNote).
`clients`-app нумеруется своим порядком.

## 5. Поверхности (Unfold admin, PL, theme-aware через `html.dark`)

**A. «Klienci» — единая база (#12).** Список = `Company` + standalone `Person` (частные лица).
Колонки: Nazwa/Imię | NIP | Typ | Telefon | e-mail. Поиск по названию/имени/NIP, фильтр по `type_supplier`.
Клик → карточка фирмы или человека.

**B. Карточка фирмы `Company` (#11).** Вертикальные панели (по образцу Zetbase `client/podgląd`):
- **Dane podstawowe** — nazwa, NIP, REGON, Typ.
- **Dane szczegółowe** — Kraj/Miasto/Województwo/Kod/Ulica, e-mail, Telefon.
- **Osoby kontaktowe** — таблица Imię | Nazwisko | e-mail | Telefon | Stanowisko | Operacje;
  кнопка «**Dodaj osobę kontaktową**» (модалка); пустое состояние = кнопка «+».
- **Powiązane zgłoszenia** — заявки этой фирмы (фильтр по `RequestMain.company`).
- **Historia kontaktów** — read-only список `ClientInteraction` (запись — паркуется).

**C. Карточка человека `Person`.** Dane osobowe; **Firmy** (связи `CompanyPersonLink` со Stanowisko);
powiązane zgłoszenia; historia kontaktów (read-only).

## 6. i18n / терминология

Код — английский; UI-лейблы (`verbose_name`, `{% trans %}`) — PL, под словарь старых сотрудников:
`Company`→«Klient»/«Firma», `Person`→«Osoba kontaktowa», `CompanyPersonLink.position`→«Stanowisko»,
`type_supplier`∈{Lokalny, Regionalny, Międzynarodowy}, `is_primary`→«Główny kontakt».
Новые строки: `gettext_lazy` в py, `{% trans %}` в шаблонах; перед завершением — makemessages→перевод PL+EN→compilemessages (часть DoD).

## 7. Definition of Done

- Модели `Company`/`Person`/`CompanyPersonLink` + миграции (структура + data-migration) применяются на чистой и на заполненной БД.
- Существующие заявки не теряют привязку к людям; `RequestMain.company` проставлен где выводится.
- Список «Klienci» + карточки фирмы/человека работают в Unfold, dark-тема не ломается.
- `Client` нигде не остаётся в коде (переименован в `Person`); UI не показывает слово «Client».
- Новые строки переведены PL+EN, `makemigrations --check` чист.
- Python-блоки, написанные Claude, помечены `# claude`.

## 8. Открытые/паркованные вопросы

- Ноты (`StepNote`) + запись разговоров + напоминания «кому написать»/`next_contact`→дедлайн — **отдельная тема**, кросс-модуль (владельцы пункта 1, #7). Решить где живёт «дата следующего контакта» до реализации #7.
- **Event-уведомления** «сотруднику пришло: клиент ответил / кто-то оставил запись» — новая фича поверх модуля `notification` (уже умеет in-app + mail + роутинг на dep_head). Downstream от write-флоу нот/ContactLog: событие появляется только когда есть запись. Порядок: структура → ноты/ContactLog write → event-уведомления.
- Филиалы `Oddziały`/`Filia` — v2.
- Дашборд #13 — отдельный спек.
- Права на `Company`/`CompanyPersonLink` в RBAC (`users/signals.py`, чужой модуль) — координация с владельцем ролей.
