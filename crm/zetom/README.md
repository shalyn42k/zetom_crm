# Документация модуля: zetom
> Обновлено с помощью ИИ (Claude Opus 4.7) — актуализация после добавления авто-тестов и бизнес-логики FSM/архивирования.

1. **Статус:** В разработке

2. **Автор:** shalyn42k

3. **Ветка:** `django/test`

---

## 1. Функциональное назначение

Основной модуль CRM. Обрабатывает весь жизненный цикл заявки — от поступления от клиента до ветвления на дочерние сущности (`Oferta`, `Zlecenie`, `Wniosek`). Включает публичную форму приёма заявок, продвижение по FSM-статусам, автоматическое архивирование родителя по состоянию детей и отображение в админ-панели Unfold.

**Текущий охват циклов:**
| Цикл | Статус |
| :--- | :--- |
| `RequestNull` → `RequestMain` | Реализован |
| `RequestMain` → `Oferta` | Реализован (создаёт запись, цена = 0, сотрудник дозаполняет) |
| `RequestMain` → `Zlecenie` | Реализован (по тому же шаблону, что и Oferta) |
| `RequestMain` → `Wniosek` | Реализован |
| FSM статусов у детей | Реализован (`new → in_progress → waiting → done`) |
| Автоматический пересчёт статуса/архива у `RequestMain` | Реализован (`update_parent`) |

---

## 2. Алгоритм работы (Логика)

### Цикл 1: Приём заявки (`RequestNull` → `RequestMain`)

1. Клиент заполняет форму на `GET /zetom/email/` (шаблон встроен в Unfold admin layout).
2. `POST /zetom/email/` — данные валидируются через `AddRequestFormNull` (польский NIP, формат телефона).
3. При успехе создаётся запись `RequestNull`.
4. Автоматически уходит email-уведомление сотруднику через `send_notification_to_staff()`.
   - Если отправка email упала — запись в БД **сохраняется**, ошибка перехватывается, форма перерисовывается.
5. После успеха форма редиректит на страницу созданной `RequestNull` в админке.
6. Сотрудник нажимает **Approve** (detail-action на `RequestNullAdmin`).
7. `approve_null_action()` (обёрнут в `@transaction.atomic`):
   - Создаёт/обновляет `RequestMain` с данными из `RequestNull` (через `update_or_create` по `from_null`).
   - Soft-удаляет `RequestNull` (django-safedelete, физически остаётся в БД).
8. Сотруднику уходит email `send_notification_approve_null()`.
9. Редирект на страницу созданного `RequestMain`.

### Цикл 2: Ветвление на дочерние сущности

Из `RequestMain` доступны три detail-action'а:

- **Oferta** → `approve_oferta_action(main_id)` → создаёт `Oferta` с `price=0`, `status=new`, `from_main=<parent>`.
- **Zlecenie** → `approve_zlecenie_action(main_id)` → аналогично (+ поле `deadline`).
- **Wniosek** → `approve_wniosek_action(main_id)` → аналогично (+ `application_number`).

После создания каждый action вызывает `update_parent(main)` — пересчитывает статус и флаг архива у родителя.

> Поле `from_main` у всех детей — `readonly_fields` в админке, заполняется только через action.

### Цикл 3: FSM статусов у детей

`services.change_status(child, new_status)` — переход ребёнка между статусами по конечному автомату:

```
new → in_progress → waiting → done
                              ↓↑
                        done ↔ waiting / in_progress
```

Запрещённые переходы (например `new → waiting`) бросают `ValueError`. В админке `Oferta`/`Zlecenie`/`Wniosek` `save_model` делегирует в `save_child_with_status()`, который при `ValueError` показывает `messages.error` и не сохраняет смену статуса.

### Цикл 4: Автоматический пересчёт родителя

`services.update_parent(parent)` дергается после любого изменения ребёнка и:

1. Собирает всех детей `RequestMain` (`oferta_set + zlecenie_set + wniosek_set`).
2. Считает приоритет статусов: `in_progress (1) > waiting (2) > new (3) > done (4)` — выбирает самый «горячий».
3. Назначает родителю этот статус.
4. Выставляет `is_archived`:
   - Нет детей → архив.
   - Все дети `done` → архив.
   - Иначе — активный.

---

## 3. Схемы и диаграммы

Диаграмм пока нет. Рекомендуемое к добавлению (положить в `zetom_crm/DOCS/DIAGRAMS/`):
- Блок-схема FSM статусов (`change_status` transitions).
- Граф сущностей (RequestNull → RequestMain → Oferta/Zlecenie/Wniosek).

---

## 4. Изменения в базе данных

Все модели наследуют `SafeDeleteModel` — физического удаления нет, записи помечаются флагом `deleted`. Стартовая структура в `migrations/0001_initial.py` (2026-04-16).

| Таблица | Ключевые поля | Связи |
| :--- | :--- | :--- |
| `zetom_requestnull` | `phone`, `email`, `company_nip`, `company_name`, `message`, `department` | — |
| `zetom_requestmain` | `+ status`, `is_archived`, `full_name`, `address` | `from_null` → `RequestNull` (OneToOne, SET_NULL) |
| `zetom_oferta` | `+ status`, `price`, `notes` | `from_main` → `RequestMain` (FK, CASCADE) |
| `zetom_zlecenie` | `+ status`, `price`, `notes`, `deadline` | `from_main` → `RequestMain` (FK, CASCADE) |
| `zetom_wniosek` | `+ status`, `notes`, `application_number` | `from_main` → `RequestMain` (FK, CASCADE) |

**Абстрактная база `RequestTemplate`** содержит общие поля (`phone`, `email`, `company_name`, `company_nip`, `message`, `department`) — таблицы не создаёт.

**Валидация:**
- `phone` — `PhoneNumberField`, регион PL (см. `PHONENUMBER_DEFAULT_REGION`).
- `company_nip` — regex `^\d{10}$` на уровне модели + `PLNIPField` на уровне формы.
- `email` — стандартный `EmailField`.

---

## 5. Информационная безопасность (ISO 27001)

### Логирование

Используется стандартный Django `LogEntry` (`django.contrib.admin.models`):
- **Что:** add / change / delete через админку; поля `action_time`, `user`, `content_type`, `object_repr`, `action_flag`, `change_message`.
- **Где:** раздел **Activity Log** в сайдбаре Unfold.
- **Защита:** `LogEntryAdmin` запрещает add/change/delete через UI — только чтение.
- **Ограничение:** `LogEntry` покрывает только действия через Admin. Публичная форма `/zetom/email/` и прямые вызовы сервисов не логируются.

> Полноценная система логирования (Full / Partial / Incident) **не реализована**, в планах.

### Целостность данных

- Soft delete через `django-safedelete`.
- `approve_null_action` и `handle_child_change` обёрнуты в `@transaction.atomic` — при сбое любого шага транзакция откатывается целиком.
- FSM `change_status` не допускает произвольного перехода между статусами — защита от случайной «перемотки».

---

## 6. Матрица прав доступа

RBAC проверяется через `user_has_perm(request.user, <perm>)` из `crm.users.utils`. В админах модуля проверки:

| Админ | view | add | change | delete |
| :--- | :--- | :--- | :--- | :--- |
| `RequestNullAdmin` | `view_requests` | `edit_requests` | `edit_requests` | `delete_requests` |
| `RequestMainAdmin` | `view_requests` | `edit_requests` | `edit_requests` | `delete_requests` |
| `OfertaAdmin` / `ZlecenieAdmin` / `WniosekAdmin` | `view_requests` | `edit_requests` | `edit_requests` | `delete_requests` |
| `LogEntryAdmin` | `view_admin_panel` | запрещено | запрещено | запрещено |

> Сами пермишены (`view_requests`, `edit_requests`, `delete_requests`, `view_admin_panel`) настраиваются через роли в модуле `users`.

---

## 7. Автоматические тесты

Тесты лежат в `crm/zetom/tests/` (Django TestCase, запускаются через `python manage.py test crm.zetom.tests`).

| Файл | Что покрывает | Кол-во |
| :--- | :--- | :---: |
| `test_models.py` | Создание моделей, `__str__`, NIP regex, дефолты, FK поведение (SET_NULL / CASCADE) | 11 |
| `test_forms.py` | `AddRequestFormNull/Main/Oferta/Zlecenie/Wniosek`: валидные/невалидные кейсы, опциональные поля, `form-control` класс | 11 |
| `test_services.py` | `change_status` (все переходы FSM), `update_parent` (приоритет статусов, архивирование), `handle_child_change`, `save_child_with_status` | 16 |
| `test_request_service.py` | `approve_null_action`, `approve_oferta/zlecenie/wniosek_action` + 404 на отсутствующих pk | 6 |
| `test_views.py` | `email_template` view: GET, POST valid → 302, POST с ошибкой нотификации, POST invalid, интеграция `send_notification_to_staff` | 5 |
| `test_admin.py` | Detail-actions `approve_action` / `oferta_action` / `zlecenie_action` / `wniosek_action`, `save_model` + FSM гейт. RBAC замокан через `user_has_perm → True` | 8 |

**Итого:** 57 тестов, все зелёные. Написаны Claude Opus 4.7 по запросу пользователя (2026-04-24).

**Что НЕ покрыто:**
- HTML-шаблоны (рендер-специфика Unfold — ломкие тесты).
- RBAC-интеграция с реальными ролями/пользователями (это зона тестов `crm.users`).
- `SignUpForm` в `forms.py` — выглядит legacy, во view не используется.

---

## 8. Инструкция для мануального тестирования

### Сценарий A: Полный цикл `RequestNull` → `RequestMain`

1. Открыть `GET /zetom/email/` (предварительно залогиниться в админке, т.к. форма встроена в Unfold layout). Форма должна отрисоваться без FOUC.
2. Заполнить: телефон `+48501600300`, NIP `7322215365`, email валидный.
3. Отправить — редирект на созданный `RequestNull` в админке.
4. Нажать **Approve** — редирект на `RequestMain`, `RequestNull` soft-удаляется.
5. Проверить Mailpit — должно прийти 2 письма (при создании `RequestNull` и при approve).

### Сценарий B: Ветвление `RequestMain` → `Oferta/Zlecenie/Wniosek`

1. Открыть `RequestMain` в Admin → **Information** → выбрать запись.
2. Нажать **Oferta** — редирект на `Oferta`, `price=0`, `from_main` автозаполнен, статус `new`.
3. Поменять статус на `in_progress` и сохранить — должно пройти. Повторить для `Zlecenie`/`Wniosek`.
4. Вернуться в `RequestMain` — статус родителя должен стать `in_progress`, `is_archived=False`.
5. Поменять статус всех детей на `done` — `RequestMain` должен автоматически уйти в архив, статус `done`.

### Сценарий C: FSM-гейт статусов

1. В `OfertaAdmin` выставить `status=new`.
2. Попробовать сразу перевести в `waiting` — должна появиться ошибка `messages.error`, статус не сохранится.
3. Допустимые последовательности: `new → in_progress → waiting → done`, и `done ↔ waiting/in_progress`.

### Сценарий D: Невалидные данные

1. Форма с NIP `123` (не 10 цифр) — должна показать ошибку валидации.
2. Форма с телефоном `abc` — аналогично.
3. При valid данных, но упавшей почте (mailpit недоступен) — запись сохраняется, форма перерисовывается.

---

### Чек-лист перед созданием Pull Request

- [ ] Выполнен `git checkout -b` из целевой ветки.
- [ ] Локальные конфликты разрешены.
- [ ] Обновлён этот MD-файл, если менялась логика / добавлялись миграции.
- [ ] Прогнаны тесты: `python manage.py test crm.zetom.tests` — все зелёные.
- [ ] Прогнан форматтер: `isort . && black .`.
- [x] Использован ИИ (Claude Opus 4.7 / Claude Code CLI) — см. пометки в коде.
