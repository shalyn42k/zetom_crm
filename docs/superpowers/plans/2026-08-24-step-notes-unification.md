# Единая лента контактов и цепочка документов — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Слить `clients.ClientInteraction` в `zetom.StepNote`, чтобы одна запись покрывала и «мы связались с клиентом», и «напомнить связаться», и была видна и с карточки документа, и с карточки персоны/фирмы.

**Architecture:** `StepNote` получает поля контакта (`kind`, `channel`, `contacted_at`, `person`, `contact_person`, `done_at`) и nullable `target`. `ClientInteraction` мигрирует в неё и удаляется. Параллельно добавляется мягкая цепочка `Oferta → Zlecenie → Wniosek` через nullable `from_oferta` / `from_zlecenie`, при этом `from_main` остаётся заполненным всегда — так существующие запросы видимости и сборки треда не трогаются.

**Tech Stack:** Django 5, Postgres, django-unfold, Alpine.js, safedelete, simple-history, django.contrib.contenttypes.

**Spec:** [docs/superpowers/specs/2026-08-24-step-notes-unification-design.md](../specs/2026-08-24-step-notes-unification-design.md)

## Global Constraints

- Тесты запускаются `python manage.py test crm.<app>` (Django `TestCase`, не pytest). Полный прогон — `python manage.py test`.
- Весь новый пользовательский текст оборачивается в `gettext_lazy` / `{% trans %}` и переводится на **PL и EN** до закрытия задачи (`makemessages` → перевод → `compilemessages`). Это часть Definition of Done, а не отдельная опция.
- Python-блоки, написанные ассистентом, помечаются комментарием `# claude` над блоком.
- Многострочные комментарии в Django-шаблонах — только `{% comment %}…{% endcomment %}`, никогда `{# … #}`.
- Дарк-тема Unfold ловится через `html.dark`, не `data-theme="dark"`.
- Данные `ClientInteraction` боевые: миграция Task 6 не мержится без зелёного теста сверки.
- `from_main` на `Zlecenie` / `Wniosek` **всегда** заполнен, даже когда заполнен `from_oferta` / `from_zlecenie`.
- Реализацию пишет пользователь; план описывает, что менять и что должен утверждать тест, без готовых сниппетов.

---

## Структура файлов

**Создаются:**

| Файл | Ответственность |
|---|---|
| `crm/zetom/services/step_notes.py` | Единственное место создания/закрытия `StepNote`; валидация инвариантов; backfill-хелперы для миграций |
| `crm/zetom/tests/test_step_notes_contact.py` | Поля контакта/напоминания, инварианты, констрейнты |
| `crm/zetom/tests/test_step_notes_service.py` | Сервис создания и закрытия записей |
| `crm/zetom/tests/test_document_chain.py` | `from_oferta` / `from_zlecenie`, авто-закрытие оферты |
| `crm/clients/tests/test_client_contact_panels.py` | Панели «Historia» и «Zaplanowane» на карточках |
| `crm/clients/services_contacts.py` | Сборка строк ленты для карточек персоны и фирмы |

**Изменяются:**

| Файл | Что |
|---|---|
| `crm/zetom/models.py:347-389` | `StepNote` — новые поля, nullable `target`, констрейнты |
| `crm/zetom/models.py:169-207` | `Zlecenie.from_oferta`, `Wniosek.from_zlecenie` |
| `crm/zetom/admin/base.py:34-40, 100-125` | Форма и action делегируют в сервис |
| `crm/zetom/admin/children.py` | Кнопки создания следующего документа в цепочке |
| `crm/zetom/services/status_orchestration.py` | Авто-закрытие оферты |
| `crm/zetom/templates/admin/zetom/shared/step_notes_modal.html` | Переключатель типа, поля контакта, классы `cc-*` |
| `crm/clients/models.py:55-111` | Удаление `ClientInteraction` |
| `crm/clients/admin.py:523, :724` | Панели читают `StepNote` |
| `crm/notification/services/followup_reminders.py:64-95` | Получатели для заметок без заявки |
| `static/clients/css/company_card.css` | Модификатор просроченного напоминания |

**Удаляются:** `static/zetom/css/step_notes.css`, `crm/clients/tests/test_interaction_admin.py`.

---

## Task 1: Поля контакта и напоминания на `StepNote`

**Files:**
- Modify: `crm/zetom/models.py:347-389`
- Create: `crm/zetom/migrations/0015_stepnote_contact_fields.py`
- Test: `crm/zetom/tests/test_step_notes_contact.py`

**Interfaces:**
- Consumes: ничего
- Produces: `StepNote.Kind` (TextChoices: `contact`, `reminder`), `StepNote.Channel` (TextChoices: `call`, `email`, `meeting`, `chat`, `other`), поля `kind`, `channel`, `contacted_at`, `person`, `contact_person`, `done_at`. `StepNote.target_content_type` / `target_object_id` становятся nullable, `text` — `blank=True`.

Значения `Channel` копируются один-в-один из `clients.ClientInteraction.Channel` (`crm/clients/models.py:58-63`), включая переводы меток — иначе Task 6 потеряет данные при маппинге.

Констрейнты в этой задаче **не** добавляются: на боевых строках `kind` ещё не проставлен, они не пройдут. Их ставит Task 3.

- [ ] **Step 1: Написать падающий тест**

В `test_step_notes_contact.py` — три теста:
1. `test_can_create_reminder_without_text_or_target` — создаётся `StepNote` с `kind=reminder`, `next_contact_at` в будущем, пустым `text` и без `target`; сохраняется без ошибки.
2. `test_can_create_contact_with_channel_and_person` — создаётся с `kind=contact`, `channel=call`, `contacted_at`, `person=<Client>`; после `refresh_from_db` все поля на месте.
3. `test_contact_person_fallback_survives_without_person_fk` — `person=None`, `contact_person="Anna z sekretariatu"` сохраняется.

- [ ] **Step 2: Прогнать, убедиться что падает**

`python manage.py test crm.zetom.tests.test_step_notes_contact -v 2`
Ожидание: FAIL, `TypeError` / `FieldError` на неизвестных полях.

- [ ] **Step 3: Добавить поля в модель**

`kind` — `CharField(max_length=20, choices=Kind.choices, default=Kind.contact)`.
`channel` — `CharField(max_length=20, choices=Channel.choices, blank=True)`.
`contacted_at` — `DateTimeField(null=True, blank=True)`.
`person` — `ForeignKey("clients.Client", on_delete=SET_NULL, null=True, blank=True, related_name="step_notes")`.
`contact_person` — `CharField(max_length=255, blank=True)`.
`done_at` — `DateTimeField(null=True, blank=True)`.
`text` — добавить `blank=True`.
`target_content_type` / `target_object_id` — добавить `null=True, blank=True`.

Все `verbose_name` — через `gettext_lazy`.

- [ ] **Step 4: Сгенерировать и проверить миграцию**

`python manage.py makemigrations zetom --name stepnote_contact_fields`
Открыть файл, убедиться: нет `AddConstraint`, есть `AlterField` на `target_content_type` / `target_object_id` / `text`.

- [ ] **Step 5: Прогнать тесты**

`python manage.py test crm.zetom -v 2` — новые PASS, существующие (особенно `test_step_notes_thread`) зелёные.

- [ ] **Step 6: Коммит**

`feat(zetom): add contact and reminder fields to StepNote`

---

## Task 2: Backfill существующих заметок

**Files:**
- Create: `crm/zetom/services/step_notes.py`
- Create: `crm/zetom/migrations/0016_backfill_stepnote_kind.py`
- Test: `crm/zetom/tests/test_step_notes_contact.py` (дополнить)

**Interfaces:**
- Consumes: поля из Task 1
- Produces: `backfill_contact_kind(step_note_model) -> int` — проставляет `kind=contact` и `contacted_at=created_at` строкам, где `contacted_at` пуст; возвращает количество обновлённых. Принимает модель параметром, чтобы миграция могла передать историческую версию через `apps.get_model`.

Логика живёт в сервисе, а не внутри миграции: иначе её нельзя протестировать напрямую. Миграция — тонкая обёртка.

- [ ] **Step 1: Написать падающий тест**

`test_backfill_sets_kind_and_contacted_at` — создать три `StepNote` с пустым `contacted_at` и одну с уже заполненным; вызвать `backfill_contact_kind(StepNote)`; проверить что вернулось `3`, что у трёх `kind == contact` и `contacted_at == created_at`, а у четвёртой `contacted_at` не перезаписан.

- [ ] **Step 2: Прогнать, убедиться что падает**

`python manage.py test crm.zetom.tests.test_step_notes_contact -v 2` — FAIL, `ImportError`.

- [ ] **Step 3: Написать сервис**

`crm/zetom/services/step_notes.py` с функцией из блока Interfaces. Обновление батчем, не построчно.

- [ ] **Step 4: Прогнать тест**

Ожидание: PASS.

- [ ] **Step 5: Написать миграцию**

`python manage.py makemigrations zetom --empty --name backfill_stepnote_kind`, внутри — `RunPython` вперёд (зовёт сервис с `apps.get_model("zetom", "StepNote")`) и `RunPython.noop` назад.

- [ ] **Step 6: Прогнать миграции и полный прогон приложения**

`python manage.py migrate` затем `python manage.py test crm.zetom`.

- [ ] **Step 7: Коммит**

`feat(zetom): backfill kind and contacted_at on existing step notes`

---

## Task 3: Инварианты и констрейнты

**Files:**
- Modify: `crm/zetom/models.py` (`StepNote.Meta.constraints`, `StepNote.clean`)
- Create: `crm/zetom/migrations/0017_stepnote_kind_constraints.py`
- Test: `crm/zetom/tests/test_step_notes_contact.py` (дополнить)

**Interfaces:**
- Consumes: Task 1 (поля), Task 2 (данные приведены)
- Produces: констрейнты `stepnote_contact_requires_contacted_at`, `stepnote_reminder_requires_next_contact_at`

Ставятся **после** Task 2: до backfill боевые строки их не пройдут.

- [ ] **Step 1: Написать падающие тесты**

1. `test_contact_without_contacted_at_is_rejected` — `StepNote.objects.create(kind=contact, contacted_at=None, ...)` внутри `assertRaises(IntegrityError)` и `transaction.atomic()`.
2. `test_reminder_without_next_contact_at_is_rejected` — то же для `kind=reminder`, `next_contact_at=None`.
3. `test_clean_gives_friendly_error_before_db` — `full_clean()` на том же объекте поднимает `ValidationError` с сообщением на поле, а не `IntegrityError`.

- [ ] **Step 2: Прогнать, убедиться что падает**

FAIL: объекты сохраняются без ошибки.

- [ ] **Step 3: Добавить `CheckConstraint` и `clean()`**

Два `CheckConstraint` в `Meta.constraints` с `Q`-условиями «либо kind другой, либо поле заполнено». `clean()` дублирует их с переводимыми сообщениями, привязанными к конкретному полю — чтобы админка показывала ошибку у поля, а не общим баннером.

- [ ] **Step 4: Миграция и прогон**

`makemigrations zetom --name stepnote_kind_constraints`, `migrate`, `python manage.py test crm.zetom`.

- [ ] **Step 5: Коммит**

`feat(zetom): enforce kind invariants on StepNote`

---

## Task 4: Сервис создания и закрытия записей

**Files:**
- Modify: `crm/zetom/services/step_notes.py`
- Modify: `crm/zetom/admin/base.py:34-40` (форма), `:100-125` (action)
- Test: `crm/zetom/tests/test_step_notes_service.py`

**Interfaces:**
- Consumes: Task 3
- Produces:
  - `create_step_note(*, author, kind, action="", text="", target=None, person=None, contact_person="", channel="", contacted_at=None, next_contact_at=None) -> StepNote` — валидирует через `full_clean()`, поднимает `ValidationError`
  - `mark_reminder_done(note, user) -> StepNote` — ставит `done_at=timezone.now()`; на записи с `kind != reminder` поднимает `ValidationError`; повторный вызов идемпотентен (не сдвигает уже проставленный `done_at`)

`StepNoteCreateForm` (`base.py:34`) расширяется полями `kind`, `channel`, `contacted_at`, `person`, `contact_person`. `text` перестаёт быть `required=True` на уровне формы — обязательность теперь зависит от `kind` и проверяется в модели.

- [ ] **Step 1: Написать падающие тесты**

1. `test_create_contact_note_persists_all_fields`
2. `test_create_reminder_without_target_is_allowed`
3. `test_create_rejects_contact_without_contacted_at` — `ValidationError`, не `IntegrityError`
4. `test_mark_reminder_done_sets_done_at`
5. `test_mark_reminder_done_is_idempotent` — второй вызов не меняет `done_at`
6. `test_mark_reminder_done_rejects_contact_note` — `ValidationError`

- [ ] **Step 2: Прогнать, убедиться что падает**

`python manage.py test crm.zetom.tests.test_step_notes_service -v 2`

- [ ] **Step 3: Реализовать сервис**

- [ ] **Step 4: Перевести `base.py` на сервис**

`step_note_create_action` перестаёт звать `StepNote.objects.create` напрямую, зовёт `create_step_note`. `ValidationError` превращается в `messages.error` с текстом ошибки, редирект на change-страницу как сейчас.

- [ ] **Step 5: Прогнать полный zetom**

`python manage.py test crm.zetom` — `test_step_notes_thread` и `test_admin` должны остаться зелёными.

- [ ] **Step 6: Коммит**

`feat(zetom): route step note creation through a service`

---

## Task 5: Напоминания без заявки уведомляют автора

**Files:**
- Modify: `crm/notification/services/followup_reminders.py:64-95`
- Test: `crm/notification/tests/test_followup_reminders_command.py` (дополнить)

**Interfaces:**
- Consumes: Task 3
- Produces: `_resolve_recipients` при `target is None` возвращает `[note.author]`, если автор активен, иначе пустой список

Сейчас `if target is None: return []` — заметка без заявки не напомнит никому, то есть напоминание, поставленное с карточки клиента, молча теряется.

- [ ] **Step 1: Написать падающий тест**

`test_reminder_without_target_notifies_author` — `StepNote` с `kind=reminder`, `target=None`, `next_contact_at` в прошлом, `reminder_sent_at=None`; после `process_due_followups()` создан один `Notification` для автора и проставлен `reminder_sent_at`.

Плюс `test_reminder_without_target_and_inactive_author_creates_nothing` — автор `is_active=False`, ничего не создано, `reminder_sent_at` остался пустым.

- [ ] **Step 2: Прогнать, убедиться что падает**

`python manage.py test crm.notification.tests.test_followup_reminders_command -v 2`

- [ ] **Step 3: Поправить `_resolve_recipients`**

Убрать ранний `return []`, перенести ветку автора выше проверки `target`.

- [ ] **Step 4: Прогнать все тесты notification**

Существующие тесты команды — обязательно зелёные.

- [ ] **Step 5: Коммит**

`fix(notification): remind the author when a note has no request`

---

## Task 6: Миграция `ClientInteraction` → `StepNote`

**Files:**
- Modify: `crm/zetom/services/step_notes.py`
- Create: `crm/clients/migrations/0010_migrate_interactions_to_step_notes.py`
- Test: `crm/clients/tests/test_interaction_migration.py`

**Interfaces:**
- Consumes: Task 3
- Produces: `migrate_client_interactions(interaction_model, step_note_model, content_type_model) -> int` — копирует все `ClientInteraction` в `StepNote`, возвращает количество

Маппинг (из спека §4): `client → person`, `request → target`, `channel → channel`, `summary → text`, `contacted_by → author`, `contact_person → contact_person`, `contacted_at → contacted_at`, `kind = contact`.

Миграция живёт в `clients` (там исходная модель), зависит от `zetom.0017`. Модели передаются параметрами, чтобы миграция подставила исторические версии.

`created_at` у `StepNote` — `auto_now_add`, при копировании перезапишется на «сейчас». Это приемлемо: хронология ленты строится по `contacted_at`, который переносится точно. Сортировка панелей меняется на `-contacted_at` в Task 7.

- [ ] **Step 1: Написать падающий тест**

`test_migrates_every_interaction_field_for_field`:
- создать 3 `ClientInteraction` — одну с `request`, одну без, одну с пустым `contact_person`
- вызвать хелпер
- проверить: `StepNote.objects.count() == 3`, вернулось `3`
- для каждой: `person`, `channel`, `text`, `author`, `contact_person`, `contacted_at` совпадают с исходной; `kind == contact`
- у первой `target` — тот самый `RequestMain`; у второй `target is None`

`test_migrates_interaction_without_author` — у `ClientInteraction.contacted_by` `null=True`; такая строка переносится, у результата `author is None`, ошибки нет.

Теста на повторный запуск нет намеренно: Django гарантирует однократное применение миграции, дедупликация здесь была бы мёртвым кодом.

- [ ] **Step 2: Прогнать, убедиться что падает**

`python manage.py test crm.clients.tests.test_interaction_migration -v 2`

- [ ] **Step 3: Реализовать хелпер**

- [ ] **Step 4: Прогнать тест**

- [ ] **Step 5: Написать миграцию**

`makemigrations clients --empty --name migrate_interactions_to_step_notes`; `dependencies` включают `("zetom", "0017_stepnote_kind_constraints")`; `RunPython` вперёд, `noop` назад.

- [ ] **Step 6: Прогнать миграции на копии боевой базы**

Не на пустой тестовой. Сверить: `SELECT count(*) FROM clients_clientinteraction` равен приросту `zetom_stepnote` с `kind='contact'` и непустым `person_id`. Расхождение — стоп, задача не закрывается.

- [ ] **Step 7: Коммит**

`feat(clients): migrate client interactions into step notes`

---

## Task 7: Панели карточек читают `StepNote`

**Files:**
- Create: `crm/clients/services_contacts.py`
- Modify: `crm/clients/admin.py:523` (персона), `:724` (фирма)
- Test: `crm/clients/tests/test_client_contact_panels.py`
- Modify: `crm/clients/tests/test_company_card_panels.py`, `crm/clients/tests/test_zetom_integration.py`

**Interfaces:**
- Consumes: Task 6
- Produces:
  - `contact_rows_for_person(client) -> list[dict]`
  - `contact_rows_for_company(company) -> list[dict]`
  - `reminder_rows_for_person(client) -> list[dict]`
  - `reminder_rows_for_company(company) -> list[dict]`

Форма строки истории сохраняется как есть (`admin.py:524-533`): ключи `data`, `kanal_label`, `sotrudnik`, `kontakt_osoba`, `zaglowek`, `summary`. Шаблоны карточек менять не нужно.

Строка напоминания добавляет ключи `due_at`, `is_overdue` (`next_contact_at < timezone.now()`), `note_pk`.

Фильтры: персона — `person=client`; фирма — `person__company_links__company=company` с `.distinct()`.

История — `kind=contact` **или** закрытое напоминание (`kind=reminder, done_at__isnull=False`), сортировка `-contacted_at` с фолбэком на `-created_at` для закрытых напоминаний (у них `contacted_at` пуст). Закрытое напоминание уходит из «Zaplanowane», но остаётся видимым в истории — так решено в спеке §5.3.

Напоминания — `kind=reminder`, `done_at__isnull=True`, сортировка `next_contact_at`.

Оба билдера должны использовать `select_related("author", "target_content_type", "person")`, иначе на карточке фирмы с десятками персон будет запрос на строку.

- [ ] **Step 1: Написать падающие тесты**

В новом `test_client_contact_panels.py`:
1. `test_person_history_shows_own_contact_notes`
2. `test_person_history_excludes_reminders`
3. `test_company_history_includes_notes_of_all_its_persons`
4. `test_company_history_excludes_notes_of_other_company_persons` — регрессия, этот кейс уже покрыт для `ClientInteraction` в `test_company_card_panels.py:54`
5. `test_reminders_panel_lists_only_open_reminders` — закрытая (`done_at` заполнен) не попадает
6. `test_closed_reminder_appears_in_history` — та же закрытая запись присутствует в `contact_rows_for_person`
7. `test_overdue_reminder_is_flagged` — `is_overdue` True для прошедшей даты, False для будущей

- [ ] **Step 2: Прогнать, убедиться что падает**

`python manage.py test crm.clients.tests.test_client_contact_panels -v 2`

- [ ] **Step 3: Написать `services_contacts.py`**

- [ ] **Step 4: Переключить билдеры контекста в `admin.py`**

Обе секции `"historia"` берут строки из сервиса. Добавить ключ `"zaplanowane"` в оба контекста.

- [ ] **Step 5: Переписать существующие тесты**

`test_company_card_panels.py` и `test_zetom_integration.py` создают `StepNote` вместо `ClientInteraction`. Смысл проверок не меняется — меняется способ создания фикстуры.

- [ ] **Step 6: Прогнать clients целиком**

`python manage.py test crm.clients`

- [ ] **Step 7: Коммит**

`refactor(clients): read contact history from step notes`

---

## Task 8: Удаление `ClientInteraction`

**Files:**
- Modify: `crm/clients/models.py:55-111` (удалить модель)
- Modify: `crm/clients/admin.py` (удалить `ClientInteractionAdmin` и инлайн)
- Create: `crm/clients/migrations/0011_delete_clientinteraction.py`
- Delete: `crm/clients/tests/test_interaction_admin.py`
- Modify: `crm/clients/tests/test_admin_add_pages.py:34-35` (убрать `interactions-*` management-form поля)

**Interfaces:**
- Consumes: Task 7 (все читатели переведены)
- Produces: ничего

- [ ] **Step 1: Убедиться, что читателей не осталось**

`grep -rn "ClientInteraction\|interactions" --include='*.py' --include='*.html' crm/`
Ожидание: только определение модели, её админка, инлайн и удаляемый тест. Любое другое совпадение — вернуться в Task 7.

- [ ] **Step 2: Удалить модель, админку, инлайн, тест**

- [ ] **Step 3: Поправить `test_admin_add_pages.py`**

Убрать четыре `interactions-*` ключа из POST-данных.

- [ ] **Step 4: Миграция**

`makemigrations clients --name delete_clientinteraction`. Убедиться, что это `DeleteModel`, а не `RemoveField` — и что она идёт **после** `0010`.

- [ ] **Step 5: Полный прогон**

`python manage.py test` — весь проект, не отдельное приложение.

- [ ] **Step 6: Коммит**

`refactor(clients): drop ClientInteraction in favour of StepNote`

---

## Task 9: Endpoints записи и закрытия с карточки клиента

**Files:**
- Modify: `crm/clients/admin.py` (`ClientAdmin.get_urls`)
- Test: `crm/clients/tests/test_client_contact_panels.py` (дополнить)

**Interfaces:**
- Consumes: Task 4 (`create_step_note`, `mark_reminder_done`), Task 7 (панели)
- Produces: url-имена `clients_client_step_note_create`, `clients_client_step_note_done`

Спек §5.2 называл второй endpoint `zetom_stepnote_done`; здесь он живёт на `ClientAdmin`, поэтому имя приведено к остальным url карточки. Правильное имя — то, что в этом блоке.

Оба endpoint-а адресуются по pk **персоны**, не фирмы. Карточке фирмы отдельные url не нужны: её «Dodaj kontakt» сначала требует выбрать персону из этой фирмы и постит на тот же `clients_client_step_note_create` с её pk.

Оба зовут сервис из `crm/zetom/services/step_notes.py`, своей логики не содержат. Гейт — `edit_clients` (как остальные write-контролы карточки; сама карточка при этом читается по `view_clients`, см. `admin.py:547-550`).

`target` берётся из POST: если передан pk заявки из связанных — GenericFK на неё, иначе `None`. Заявка, не связанная с этим клиентом, отвергается — иначе через подставленный pk можно прицепить заметку к чужой заявке.

- [ ] **Step 1: Написать падающие тесты**

1. `test_create_contact_from_person_card` — POST создаёт `StepNote` с `person=client`
2. `test_create_contact_with_related_request_sets_target`
3. `test_create_contact_rejects_unrelated_request` — 403 либо ошибка формы, заметка не создана
4. `test_view_only_user_cannot_create_note` — пользователь с `view_clients` без `edit_clients` получает 403
5. `test_done_endpoint_closes_reminder` — после POST `done_at` заполнен, запись ушла из `reminder_rows_for_person`
6. `test_get_request_does_not_create_note` — GET редиректит, ничего не создаёт

- [ ] **Step 2: Прогнать, убедиться что падает**

- [ ] **Step 3: Добавить endpoints**

Паттерн — как `step_note_create_action` в `crm/zetom/admin/base.py:100`: только POST, проверка прав, сервис, `messages`, редирект на карточку.

- [ ] **Step 4: Прогнать clients**

- [ ] **Step 5: Коммит**

`feat(clients): log contacts and close reminders from client cards`

---

## Task 10: Цепочка документов

**Files:**
- Modify: `crm/zetom/models.py:169-207`
- Create: `crm/zetom/migrations/0018_document_chain.py`
- Test: `crm/zetom/tests/test_document_chain.py`

**Interfaces:**
- Consumes: ничего
- Produces: `Zlecenie.from_oferta` (FK `Oferta`, null, `SET_NULL`, `related_name="zlecenia"`), `Wniosek.from_zlecenie` (FK `Zlecenie`, null, `SET_NULL`, `related_name="wnioski"`)

`related_name` на `Oferta` / `Zlecenie` свободны: существующие `ofertas` / `zlecenia` / `wnioski` висят на `clients.Client` через M2M, не на документах.

- [ ] **Step 1: Написать падающие тесты**

1. `test_zlecenie_can_be_created_without_oferta` — `from_oferta=None` сохраняется (мягкая цепочка)
2. `test_zlecenie_links_back_to_oferta` — `oferta.zlecenia.all()` содержит созданное
3. `test_deleting_oferta_keeps_zlecenie` — `SET_NULL`, злецение живо, `from_oferta` пуст, `from_main` не тронут
4. Те же три для `Wniosek.from_zlecenie`

- [ ] **Step 2: Прогнать, убедиться что падает**

- [ ] **Step 3: Добавить поля и миграцию**

- [ ] **Step 4: Прогнать zetom**

- [ ] **Step 5: Коммит**

`feat(zetom): add soft Oferta -> Zlecenie -> Wniosek chain`

---

## Task 11: Создание следующего документа из карточки

**Files:**
- Modify: `crm/zetom/admin/children.py`
- Modify: `crm/zetom/services/status_orchestration.py`
- Modify: `crm/zetom/templates/admin/zetom/oferta/change_form.html`, `.../zlecenie/change_form.html`
- Test: `crm/zetom/tests/test_document_chain.py` (дополнить)

**Interfaces:**
- Consumes: Task 10
- Produces: url-имена `zetom_oferta_zlecenie_action`, `zetom_zlecenie_wniosek_action`; `close_oferta_on_zlecenie(oferta, user)` в `status_orchestration`

Действия повторяют существующий паттерн `zetom_requestmain_zlecenie_action` (см. `crm/zetom/admin/requestmain.py` и кнопки в `_partials/documents.html:72-78`).

Создаваемый документ наследует от родителя снапшот контакта (`first_name`, `last_name`, `phone`, `email`, `company_name`, `company_nip`, `departments`, `source`) — как это делают существующие действия с карточки заявки.

**`from_main` копируется из родителя обязательно** (`oferta.from_main`), иначе документ выпадет из `_step_note_targets` и из фильтра видимости.

Авто-закрытие: создание злецения переводит оферту в `done`. Для `Wniosek` из `Zlecenie` симметричного правила **нет** — так решено в спеке §3.2.

- [ ] **Step 1: Написать падающие тесты**

1. `test_zlecenie_action_sets_from_oferta_and_from_main`
2. `test_zlecenie_action_closes_the_oferta` — статус оферты `done`
3. `test_zlecenie_action_copies_contact_snapshot`
4. `test_wniosek_action_sets_from_zlecenie_and_does_not_close_it` — статус злецения не изменился
5. `test_zlecenie_action_requires_edit_permission` — 403 без `edit_requests`

- [ ] **Step 2: Прогнать, убедиться что падает**

- [ ] **Step 3: Добавить actions в `children.py`**

- [ ] **Step 4: Добавить `close_oferta_on_zlecenie` в `status_orchestration.py`**

Перевод статуса — через существующий FSM `status_manager`, не присваиванием поля напрямую.

- [ ] **Step 5: Добавить кнопки в шаблоны**

- [ ] **Step 6: Прогнать zetom**

- [ ] **Step 7: Коммит**

`feat(zetom): create the next document from an offer or order`

---

## Task 12: Модалка — переключатель типа и стиль `cc-*`

**Files:**
- Modify: `crm/zetom/templates/admin/zetom/shared/step_notes_modal.html`
- Modify: `crm/zetom/admin/base.py` (`Media`), контекст модалки
- Modify: `static/clients/css/company_card.css`
- Delete: `static/zetom/css/step_notes.css`
- Test: `crm/zetom/tests/test_step_notes_thread.py` (дополнить)

**Interfaces:**
- Consumes: Task 4 (форма и сервис)
- Produces: контекст модалки получает `step_notes_persons` — список персон, доступных как собеседники

Источник персон на странице документа: персоны заявки (`RequestMain.clients`) плюс персоны связанной фирмы (`RequestMain.company` → `CompanyPersonLink`), дедуплицированные.

`sn-*` классы заменяются на `cc-*` из `company_card.css`: `.overlay/.modal/.modal-h/.modal-b/.modal-f/.modal-x` для формы, `.hist/.hev/.dot/.line/.hbody/.hmeta/.htext` для ленты. Правила там заскоплены на `.cc-stage` — модалку завернуть в один такой div.

`BaseRequestAdmin.Media` перестаёт грузить `zetom/css/step_notes.css`, начинает грузить `clients/css/company_card.css`.

В `company_card.css` добавляется модификатор просроченного напоминания — красная точка вместо `--green-bright` у `.hev .dot`. Обязательно проверить в дарк-теме через `html.dark`.

Кнопки «+ добавить персону» в модалке нет — вместо неё ссылка на карточку клиента.

- [ ] **Step 1: Написать падающий тест**

1. `test_modal_context_lists_request_persons` — контекст содержит персон заявки и персон её фирмы, без дублей
2. `test_modal_context_excludes_unrelated_persons`
3. `test_modal_renders_kind_toggle` — `assertContains` на оба варианта переключателя

- [ ] **Step 2: Прогнать, убедиться что падает**

- [ ] **Step 3: Добавить `step_notes_persons` в `_build_step_notes_context`**

- [ ] **Step 4: Переписать шаблон**

Переключатель типа наверху формы. При «Zapisz kontakt» — канал, дата разговора, собеседник (select + текстовый фолбэк), что сделано, заметка, дата следующего контакта. При «Zaplanuj przypomnienie» — дата, что напомнить, заметка. Переключение — Alpine `x-show`, как в существующих модалках `clients`.

- [ ] **Step 5: Переключить `Media`, удалить `step_notes.css`**

- [ ] **Step 6: Проверить глазами обе темы**

Светлая и `html.dark`, на карточке заявки и на карточке дочернего документа.

- [ ] **Step 7: Прогнать zetom**

- [ ] **Step 8: Коммит**

`feat(zetom): rework the work log modal into contact and reminder modes`

---

## Task 13: Панели «Zaplanowane» и «Dodaj kontakt» на карточках

**Files:**
- Modify: `crm/clients/templates/admin/clients/client/person_card.html`
- Modify: `crm/clients/templates/admin/clients/company/company_card.html`
- Test: `crm/clients/tests/test_person_card.py`, `crm/clients/tests/test_company_card.py` (дополнить)

**Interfaces:**
- Consumes: Task 7 (`zaplanowane` в контексте), Task 9 (endpoints), Task 12 (разметка модалки)
- Produces: ничего

Секция «Zaplanowane» — над «Historia kontaktów», на тех же `.hist/.hev`. Каждая строка: дата, что напомнить, кнопка-галочка на `clients_client_step_note_done`. Просроченные — с модификатором из Task 12.

Кнопка «Dodaj kontakt» в шапке панели «Historia» открывает модалку из Task 12, форма постит на `clients_client_step_note_create`. На карточке фирмы модалка дополнительно требует выбрать персону из этой фирмы — pk этой персоны и уходит в url.

Пустое состояние обеих секций — как у существующих панелей карточки (`.empty`).

- [ ] **Step 1: Написать падающие тесты**

1. `test_person_card_renders_reminders_section`
2. `test_person_card_hides_reminders_section_when_empty` — секция не рендерится или показывает пустое состояние, но не ломает страницу
3. `test_person_card_shows_add_contact_button_for_editor`
4. `test_person_card_hides_add_contact_button_for_viewer` — `view_clients` без `edit_clients`
5. Те же для карточки фирмы

- [ ] **Step 2: Прогнать, убедиться что падает**

- [ ] **Step 3: Добавить разметку в оба шаблона**

- [ ] **Step 4: Проверить глазами обе темы**

- [ ] **Step 5: Прогнать clients**

- [ ] **Step 6: Коммит**

`feat(clients): add reminders panel and contact logging to client cards`

---

## Task 14: i18n PL + EN

**Files:**
- Modify: `locale/pl/LC_MESSAGES/django.po`, `locale/en/LC_MESSAGES/django.po`

**Interfaces:**
- Consumes: все предыдущие задачи
- Produces: скомпилированные каталоги

Терминология из спека §8:

| Смысл | PL | EN |
|---|---|---|
| Контакт | Kontakt | Contact |
| Напоминание | Przypomnienie | Reminder |
| Запланированные | Zaplanowane | Scheduled |
| История контактов | Historia kontaktów | Contact history |
| Собеседник | Rozmówca | Interlocutor |
| Канал | Kanał | Channel |
| Дата разговора | Data rozmowy | Contact date |
| Следующий контакт | Następny kontakt | Next contact |
| Добавить контакт | Dodaj kontakt | Add contact |

- [ ] **Step 1: Собрать строки**

`python manage.py makemessages -l pl -l en`

- [ ] **Step 2: Проверить, что ничего не пропущено**

`grep -c "msgstr \"\"" locale/pl/LC_MESSAGES/django.po` — сравнить с количеством новых строк. Непереведённых новых остаться не должно.

- [ ] **Step 3: Перевести**

Метки `Kind` и `Channel`, заголовки панелей, кнопки, сообщения `messages.error` из Task 4 и Task 9, сообщения `ValidationError` из Task 3.

- [ ] **Step 4: Скомпилировать**

`python manage.py compilemessages`

- [ ] **Step 5: Проверить глазами**

Карточка персоны и карточка заявки при `LANGUAGE_CODE = "pl"` и `"en"`.

- [ ] **Step 6: Полный прогон**

`python manage.py test`

- [ ] **Step 7: Коммит**

`i18n(zetom,clients): translate contact log and reminder strings`

---

## Проверка перед закрытием

Из спека §9:

- [ ] Все тесты зелёные: `python manage.py test`
- [ ] `grep -rn "ClientInteraction" crm/` пуст
- [ ] Боевые данные перенесены, количества сверены (Task 6 Step 6)
- [ ] Напоминание ставится и закрывается с карточки персоны и с карточки документа
- [ ] Контакт с карточки клиента виден в ленте связанной заявки и наоборот
- [ ] `static/zetom/css/step_notes.css` удалён, модалка выглядит как остальные модалки `clients`
- [ ] Новые строки переведены на PL и EN, `compilemessages` прогнан
- [ ] Python-блоки, написанные ассистентом, помечены `# claude`
