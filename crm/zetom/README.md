# Документация модуля: zetom

> Обновлено: после сплита `admin.py` в `admin/` package, добавления
> `RequestSource` / first_name+last_name / collapsible UI, кастомного
> change-view RequestMain и Trash-флоу. Часть зон (status_manager,
> users) живут в соседних приложениях — см. ссылки ниже.

1. **Статус:** В разработке
2. **Автор:** shalyn42k
3. **Ветка:** `django/test`

---

## 1. Функциональное назначение

Основной модуль CRM. Жизненный цикл заявки: публичная форма приёма
(`RequestNull`) → утверждение в админке (`RequestMain`) → создание
дочерних документов (`Oferta` / `Zlecenie` / `Wniosek`) → авто-пересчёт
родительского статуса по детям → soft-delete → опциональное
восстановление или физическое удаление через Trash.

Вокруг этого построен кастомный change-view RequestMain (двухколоночный
layout с collapsible-карточками, persist-стейт через `localStorage`),
status-flow с reason-form и audit-trail (`StatusHistory`).

**Текущий охват:**

| Цикл | Статус |
|---|---|
| `RequestNull` (public site form) → `RequestMain` (Approve action) | ✓ |
| `RequestMain` → `Oferta` / `Zlecenie` / `Wniosek` (Documents-карточка) | ✓ |
| FSM статусов у детей (`new → in_progress → waiting → done`) | ✓ |
| Auto-пересчёт статуса родителя (`update_parent` в status_manager) | ✓ |
| Manual смена статуса родителя через Apply (свободные + reason-required) | ✓ |
| Soft-delete + Trash (Restore / Hard delete) | ✓ |
| Multi-department per Request (ArrayField) | ✓ |
| Многоуровневые child-документы (несколько Oferta / Zlecenie / Wniosek на одного родителя) | ✓ |
| Source channel (phone / email / site / main / manual / other) | ✓ |
| Status history timeline на change-view | ✓ |
| Sticky состояние карточек (open/closed) per-user-per-request | ✓ |

---

## 2. Алгоритм работы (логика)

### 2.1 Приём заявки (`RequestNull` → `RequestMain`)

1. Клиент заполняет публичную форму на `GET /zetom/email/`. Поля:
   First name, Last name, Phone, Email, Company name, Message.
   **NIP не требуется** на публичной форме.
2. `POST /zetom/email/` валидируется через `AddRequestFormNull`
   (`PhoneNumberField` PL, обязательны first/last/phone/email).
3. View (`crm.zetom.views.email_template`) проставляет
   `source = RequestSource.SITE` и сохраняет `RequestNull`.
4. Уходит email-уведомление сотруднику
   (`send_notification_to_staff`). Если письмо упало — запись остаётся,
   ошибка сообщается на форме.
5. Стафф открывает запись в админке (`Validation Window`, raw
   `RequestNullAdmin`) и нажимает **Approve** (detail-action).
   - Add-кнопка для `RequestNull` отключена (`has_add_permission=False`)
     — заявки создаются только публично.
6. `approve_null_action()` (`@transaction.atomic`):
   - `RequestMain.objects.update_or_create(from_null=null_obj, ...)`
     копирует first_name / last_name / phone / company_name /
     company_nip / email / message / source.
   - Soft-удаляет `RequestNull` (django-safedelete).
7. Email-уведомление об approve.
8. Редирект на change-view созданного `RequestMain`.

### 2.2 Кастомный change-view `RequestMain`

Шаблон `admin/zetom/requestmain/change_form.html`. Состоит из:

**Левая колонка (всегда видна):**
- **Client** — Avatar + name+NIP summary, ниже dl/dt/dd с editable
  полями NIP / Company / First name / Last name. Placeholder под
  будущую модель Client (FK).
- **Client information** — crispy-Layout: email/phone (Row), address,
  message.

**Правая колонка (collapsible с `$persist`):**
- **Assigned users** — list юзеров с Owner-бейджем, × для unassign,
  ниже select свободных + `+ Add` (POST к `assign_user_action`).
- **Status grid** — 6 radio-кнопок (active/open/closed/inactive/
  cancelled/deleted) с цветными чекмарками + Apply.
- **Departments** — `.rm-dept-row`-list с зелёной подсветкой
  собственного департамента юзера (`--mine`). Add/remove через select +
  `+ Add` / × кнопки.
- **Documents** — три блока (Offer / Order / Application). Если
  документов нет — Create. Если есть — select со списком кодов
  `OFR-YYYY-NNNN` / `ZLC-...` / `WNI-...`, кнопка View открывает
  выбранный, `+` создаёт новый.
- **History** — timeline записей `StatusHistory` со status-pill,
  reason'ом и `naturaltime` («2 minutes ago»).

Header: REQ-tag + status pill + source badge (`via Phone` etc.).

### 2.3 Status flow

Manual смена статуса идёт через `apply_status_action`
(`/admin/zetom/requestmain/<pk>/apply-status/`). Логика в
`crm.zetom.services.status_orchestration.apply_status_change`
(`@transaction.atomic`):

| `new_status` | Поведение |
|---|---|
| `cancelled` | требует reason; делегирует в `cancel_request` (status_manager) — пишет `StatusHistory`, статус меняется |
| `deleted` | требует reason; делегирует в `delete_request` + дополнительно `obj.delete()` (safedelete cascade на дочки) — запись уходит в Trash |
| `inactive` | требует reason; локальный `inactive_request` (mirror cancel/delete) пишет `StatusHistory` |
| `active` / `open` / `closed` | свободный переход; `obj.save()` + `StatusHistory` запись с пустым reason'ом |

Reason-required ветки открывают `reason_form.html` (тот же шаблон —
`form` с `<textarea name="reason">` и hidden `new_status`).

Стоковая Django Delete-кнопка в submit-баре (`delete_model` /
`delete_queryset` overrides) теперь **тоже** flip'ает status в
`deleted` перед safedelete'ом, чтобы Trash и main-list были
консистентны.

### 2.4 Auto-пересчёт родителя

`update_parent(parent)` в `status_manager.services.status_service`
вызывается из `handle_child_change` после любой смены статуса ребёнка.
Алгоритм:

- Если `parent.status` ∈ {cancelled, deleted} → ранний выход
  (защищены от перезаписи).
- Иначе: считает `parent.oferta_set + zlecenie_set + wniosek_set`,
  выбирает самый «горячий» статус (in_progress > waiting > new > done),
  выставляет родителю.
- Если все три типа child-документов созданы и все `done` →
  `parent.status = closed`.

> Известное ограничение: `active`/`open`/`closed`/`inactive` ручной
> Apply-выбор может быть **затёрт** child-логикой при следующем
> `handle_child_change`. Защищены только cancelled/deleted. Решение
> «manual_status flag» — отложено, см. `DOCS/manual_status_override_todo.md`.

### 2.5 Trash (`DeletedRequest`)

Proxy-модель на `RequestMain`, queryset = `RequestMain.deleted_objects`.
Read-only change-view с собственным `submit_buttons_bottom`:

- **Restore** (зелёная) — `obj.undelete()` + `status=active` +
  `StatusHistory` («Restored from trash»). Редирект на change-view
  RequestMain.
- **Hard delete** (красная, JS confirm) —
  `obj.delete(force_policy=HARD_DELETE)`. Редирект на trash list.

Custom URL'ы регистрируются в `DeletedRequestAdmin.get_urls()`. Обе
обёрнуты в `@transaction.atomic`.

---

## 3. Структура кода

```
crm/zetom/
├── admin/                         # split admin package
│   ├── __init__.py                # re-exports + auto-loads submodules
│   ├── base.py                    # BaseRequestAdmin, ReasonForm,
│   │                              # DepartmentsDisplayMixin
│   ├── log.py                     # LogEntryAdmin (read-only)
│   ├── requestnull.py             # RequestNullAdmin (Add disabled)
│   ├── requestmain.py             # RequestMainAdmin (~320 lines —
│   │                              # custom change-view, status flow,
│   │                              # all custom URLs, doc creation)
│   ├── children.py                # OfertaAdmin / ZlecenieAdmin /
│   │                              # WniosekAdmin
│   └── deletedrequest.py          # DeletedRequestAdmin (Trash)
│
├── models.py                      # RequestTemplate (abstract) +
│                                  # RequestNull / RequestMain /
│                                  # Oferta / Zlecenie / Wniosek /
│                                  # DeletedRequest (proxy)
├── forms.py                       # AddRequestFormNull / Main /
│                                  # AddOferta / AddZlecenie /
│                                  # AddWniosek + TemplateForm base
├── views.py                       # email_template (public form)
├── urls.py                        # /zetom/email/ route
│
├── services/
│   ├── request_service.py         # approve_null_action /
│   │                              # _approve_child / *_action
│   ├── status_orchestration.py    # apply_status_change (zetom-side
│   │                              # FSM router); inactive_request
│   └── visibility.py              # visible_requests_for (RBAC filter
│                                  # for specialists)
│
├── templates/
│   ├── admin/zetom/requestmain/
│   │   ├── change_form.html       # custom change-view
│   │   ├── reason_form.html       # cancel / delete / inactive reason
│   │   └── _partials/             # client_card, client_information,
│   │                              # source_picker, assigned_users,
│   │                              # status_grid, departments,
│   │                              # documents, history_card
│   ├── admin/zetom/deletedrequest/
│   │   └── change_form.html       # trash read-only view + submit-bar
│   └── zetom/email_template.html  # public site form
│
├── static/zetom/                  # public form CSS, bg.png
└── migrations/0001_initial.py     # single squashed migration
```

Соседние приложения:
- `crm/status_manager/` — `StatusHistory` модель, `RequestStatus` /
  `Status` enums, `cancel_request` / `delete_request` /
  `update_parent` / `change_status`. **Tightly coupled с zetom**
  (cross-app FK + знание дочек). См. `DOCS/status_manager_coupling.md`
  если будет создан.
- `crm/users/` — `UserProfile` (с `department`), `Role`, `Permission`,
  `user_has_perm` helper. Используется в RBAC zetom-админок.
- `crm/notification/` — email-уведомления при создании RequestNull /
  approve.

---

## 4. Модели и схема

Все модели наследуют `SafeDeleteModel` (`SOFT_DELETE_CASCADE`) —
физического удаления нет, ставится `deleted_at`.

### Абстрактная база `RequestTemplate`

| Поле | Тип | Заметки |
|---|---|---|
| `source` | `CharField(choices=RequestSource)` | default `OTHER` |
| `assigned_to` | `M2M(User)` | related_name `+` |
| `created_at` / `updated_at` | `DateTimeField` | auto |
| `first_name` / `last_name` | `CharField(50, null=True)` | разбито из бывшего `full_name` |
| `phone` | `PhoneNumberField` | required |
| `email` | `EmailField` | required |
| `company_name` | `CharField(50, null=True)` | optional |
| `company_nip` | `CharField(10, null=True, regex=^\d{10}$)` | nullable (на public form необязательно) |
| `message` | `TextField` | optional |
| `departments` | `ArrayField(CharField, choices=DepartmentsVariants)` | default `[]` |

`@property full_name` — derived: `f"{first_name} {last_name}"`.

### Конкретные модели

| Модель | Доп. поля | Ключевые связи |
|---|---|---|
| `RequestNull` | — | (только public-intake) |
| `RequestMain` | `status` (RequestStatus), `address` | `from_null` → `RequestNull` (OneToOne, SET_NULL) |
| `Oferta` | `status` (Status), `price`, `notes` | `from_main` → `RequestMain` (FK, CASCADE) |
| `Zlecenie` | `status`, `price`, `notes`, `deadline` | `from_main` → `RequestMain` |
| `Wniosek` | `status`, `notes`, `application_number` | `from_main` → `RequestMain` |
| `DeletedRequest` | proxy(`RequestMain`) | qs = `RequestMain.deleted_objects` |

### Enums

- `RequestStatus` (status_manager): `active` / `open` / `closed` /
  `inactive` / `cancelled` / `deleted`.
  - `inactive` запланирован к сносу (см. todo-doc).
- `Status` (status_manager, для дочек): `new` / `in_progress` /
  `waiting` / `done`.
- `RequestSource` (zetom): `phone` / `email` / `site` / `main` (created
  from parent) / `manual` (admin Add) / `other`.
- `DepartmentsVariants` (zetom): 7 значений (Research Team /
  Calibration Team / Length and Angle Lab / Electrical Lab /
  Mechanical Lab / Heating Equipment Lab / Technical Office).

### Миграции

Сейчас одна `0001_initial.py` — schema squash сделан после крупных
schema-changes (source / first-last / departments-array / English
labels). Старая история склеена.

---

## 5. Информационная безопасность

### Логирование

Два независимых журнала:

1. **`StatusHistory`** (status_manager) — записи смен статуса
   `RequestMain` с reason'ом и `changed_by`. Заполняется
   `cancel_request` / `delete_request` / `inactive_request` /
   `apply_status_change` (свободные переходы) / `restore_action`. Отображается
   на change-view в History-карточке (timeline).
2. **Django `LogEntry`** (`django.contrib.admin.models`) — стандартный
   admin-журнал add/change/delete. Только действия через админку.
   Доступен в **Activity Log** (sidebar). `LogEntryAdmin` запрещает
   add/change/delete — только просмотр.

> Полноценная event-log система (assign user, add department, etc.) —
> не реализована. См. вариант B в обсуждении History.

### Целостность данных

- Soft-delete через django-safedelete (`SOFT_DELETE_CASCADE` на
  RequestTemplate — каскад на дочки при удалении родителя).
- `@transaction.atomic` на:
  - `apply_status_change`,
  - `RequestMainAdmin.delete_model` / `delete_queryset`,
  - `DeletedRequestAdmin.restore_action` / `hard_delete_action`,
  - `approve_null_action`,
  - `RequestNullAdmin.approve_action` (через `@transaction.atomic`
    декоратор).
- FSM `change_status` (status_manager) запрещает произвольные переходы
  между статусами child'а — `ValueError` при попытке.

---

## 6. Матрица прав (RBAC)

`user_has_perm(request.user, <perm>)` из `crm.users.utils`.

| Админ | view | add | change | delete |
|---|---|---|---|---|
| `RequestNullAdmin` | `view_requests` | **disabled** | `edit_requests` | `delete_requests` |
| `RequestMainAdmin` | `view_requests` | `edit_requests` | `edit_requests` | `delete_requests` |
| `OfertaAdmin` / `ZlecenieAdmin` / `WniosekAdmin` | `view_requests` | `edit_requests` | `edit_requests` | `delete_requests` |
| `DeletedRequestAdmin` (proxy) | `view_requests` | **disabled** | `view_requests` (для action'ов) | **disabled** |
| `LogEntryAdmin` | always true | disabled | disabled | disabled |

`visible_requests_for(user, qs)` (`services/visibility.py`) дополнительно
сужает changelist'ы:
- `is_superuser` → весь queryset.
- роль `specialist` → только `assigned_to=user` или `departments
  __contains [profile.department]`.
- остальные роли (admin / department_head / auditor / all_seeing) →
  весь queryset.

---

## 7. Тесты

`crm/zetom/tests/` — Django TestCase. Запуск: `python manage.py test
crm.zetom.tests`.

> ⚠️ **Тесты сейчас сломаны** после schema-rework
> (`full_name → first_name/last_name`, `department → departments`).
> Часть модулей не загружается из-за устаревшего импорта
> `crm.zetom.services.statuses` (модуль был перенесён в `status_manager`),
> часть assertion'ов падает на новых полях. Требуется обновление —
> отдельная задача.

Скоуп существующих тестов (после фикса):

| Файл | Что покрывает |
|---|---|
| `test_models.py` | Создание моделей, NIP regex, дефолты, FK поведение |
| `test_forms.py` | `AddRequestForm*` — валидные / невалидные кейсы |
| `test_services.py` | `change_status` (FSM), `update_parent` |
| `test_request_service.py` | `approve_null_action`, `approve_*_action` |
| `test_views.py` | `email_template` view (GET / POST / errors) |
| `test_admin.py` | Detail-actions, RBAC mock |

**Что НЕ покрыто:**
- HTML-шаблоны (custom change-view / partials).
- `apply_status_change` reason-flow и status-переходы.
- Trash flow (Restore / Hard delete).
- `assign_user_action` / `add_department_action` / прочие custom URL'ы.

---

## 8. Manual testing

### Сценарий A: публичная форма → Approve

1. `GET /zetom/email/` (логин не нужен для самой формы; для приёмки —
   нужен).
2. Заполнить: First/Last/Phone/Email/Company/Message. NIP не нужен.
3. Submit — редирект на `RequestNull` change-view в админке.
4. **Approve** action — soft-удаляет null, создаёт RequestMain с
   `source=site`. Редирект на RequestMain change-view.

### Сценарий B: смены статуса

1. Открыть RequestMain change-view.
2. Status grid → `Open` → Apply (свободный) → success-флеш + redirect.
   Запись в History.
3. Status grid → `Cancelled` → Apply → reason-form → Confirm.
   `StatusHistory` пишет cancel.
4. Status grid → `Deleted` → reason → Confirm. Запись уходит в Trash.

### Сценарий C: Trash flow

1. `/admin/zetom/deletedrequest/` — список soft-deleted записей.
2. Открыть запись. Должны быть видны: callout-banner, header с status
   pill, Client, Client info, collapsible Users / Departments /
   Documents.
3. **Restore** — запись возвращается в Information с `status=active`.
4. **Hard delete** — confirm prompt → запись физически удалена из БД.

### Сценарий D: Documents

1. На RequestMain открыть Documents-карточку (collapsible).
2. `+` под Offer → создаётся Oferta с `from_main` родителя,
   `source=main`. Редирект обратно на RequestMain (не на Oferta).
3. Создать ещё один Offer. Должен появиться select с двумя кодами
   `OFR-2026-NNNN`. Выбрать любой → View → открывает выбранный.

### Сценарий E: Departments / Users

1. В Departments select выбрать один → `+ Add`. Появляется в pill-list.
   Если совпадает с `request.user.profile.department` — подсвечен зелёным.
2. `×` на pill → удаляет.
3. Аналогично Users.
4. Обновить страницу — состояние карточек (open/closed) сохраняется
   per-user-per-request в localStorage.

---

## 9. Чек-лист перед PR

- [ ] `python manage.py check` — clean.
- [ ] `djlint crm/zetom/templates/` — clean.
- [ ] Тесты прогнаны (когда починятся): `python manage.py test crm.zetom.tests`.
- [ ] Форматтер: `isort . && black .`.
- [ ] Этот README актуализирован если менялась логика / схема / структура.
- [x] AI-помощь использована — Claude Opus 4.7 (Claude Code CLI).
