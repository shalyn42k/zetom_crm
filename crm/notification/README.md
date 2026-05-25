# Модуль `notification`

1. **Статус:** В разработке

2. **Автор:** Tymur (часть кода написана с помощью ИИ — отмечена `# claude` в коде)

3. **Ветка:** `django/test`

---

## 1. Функциональное назначение

Модуль централизованно управляет двумя каналами уведомлений в CRM:

- **mail** — реальные email-письма через SMTP (клиенту по статусу документа, стаффу по новой/валидированной заявке, по кнопке "Send mail" в форме RequestMain).
- **inapp** — внутрисистемные уведомления, которые показываются в шапке (красный кружок-счётчик на аватаре) и в кастомном inbox'е.

Получатели всегда **резолвятся динамически**: dep_head'ы отделов, привязанных к заявке → fallback на админов. Никаких захардкоженных адресов в коде.

## 2. Алгоритм работы (Логика)

1. **Триггер** — событие в системе вызывает функцию из `services/`:
   - View: при сабмите сайтовой формы (`send_notification_to_staff`), валидации Null (`send_notification_approve_null`), нажатии "Send mail" (`send_document_to_staff` / `send_freeform_to_client`) или "Request review" (`inapp_service.create_inapp`).
   - Сигнал: переход документа в `Status.in_progress` (`send_document_to_client`), смена `RequestMain.status` (inapp `request_status_changed`).
2. **Резолв получателей** — функция из `services/recipients.py` (`dep_heads_or_admins`) возвращает список User'ов: department_head'ы, чьи `head_of_departments` пересекаются с `Req.departments`; если пусто — все active admin'ы (`role.code == "admin"` ИЛИ `is_superuser=True`).
3. **Рендер шаблона** — `render_to_string("notification/mail/.../X.txt", context)`. Первая непустая строка = тема/title, остальное = тело.
4. **Отправка / запись**:
   - mail: для каждого получателя создаётся запись `EmailNotification(status=PENDING)`, затем `send_mail`. На успех — `SENT` + `sent_at`. На SMTP-исключение — `FAILED` + `status_reason`. Исключение **не пробрасывается** наверх (SMTP-фейл не валит view/сигнал).
   - inapp: создаётся `Notification` на каждого получателя. Шаблон **не рендерится сейчас** — `payload` JSON хранит весь контекст, UI рендерит шаблон лениво при показе.
5. **UI**:
   - Счётчик непрочитанных пересчитывается в `context_processor` на каждом запросе через индекс `(recipient, is_read)`.
   - Красный кружок-бейдж поверх аватара в sidebar'е через override `templates/unfold/helpers/navigation_user.html`.
   - Кастомная inbox-страница `/notifications/` (см. `crm/notification/views.py` + `templates/notification/inbox.html`), реализованная по handoff-дизайну: фильтры All/Unread, kind-chips, day-grouping, пагинация по 10. Доступна из ACCOUNT-dropdown и из sidebar'а ("Inbox").
   - Клик по уведомлению → POST `mark_read` → 302 редирект на target (через `target.get_absolute_url()` или admin change-view fallback). Шаблон рендерится лениво в `utils.render_notification(n)`.

## 3. Схемы и диаграммы

Пока без отдельной диаграммы. Если будет нужна — положить в `DOCS/DIAGRAMS/notification_flow.{drawio,svg}`. Для быстрого понимания структуры есть таблица "триггер → канал → получатели → шаблон" в [TODO.md](../../TODO.md#матрица-триггер--канал--получатели). Также есть отдельный бриф под UI: [DOCS/notification_ui_brief.md](../../DOCS/notification_ui_brief.md).

## 4. Изменения в базе данных

### Новые/изменённые таблицы

- **`notification_notification`** — inapp-уведомления. Полностью переработана:
  - `recipient` (FK → `auth_user`)
  - `actor` (FK → `auth_user`, nullable, `on_delete=SET_NULL`)
  - `kind` (CharField, choices из `NotificationKind`)
  - `template_name` (CharField, путь к .txt шаблону)
  - `payload` (JSONField, контекст для ленивого рендера)
  - `target_content_type` + `target_object_id` (GenericForeignKey на любую модель)
  - `is_read` / `read_at` (BooleanField + DateTimeField)
  - индексы: `(recipient, is_read)` для счётчика, `(recipient, -created_at)` для inbox
- **`notification_emailnotification`** — лог email-отправок. Полностью переработана:
  - `recipient_email` (EmailField — без FK на User, потому что клиенту нет учётки)
  - `actor` (FK → `auth_user`, nullable)
  - `template_name`, `subject` (CharField)
  - `payload` (JSONField)
  - `status` (PENDING / SENT / FAILED), `status_reason`, `sent_at`
- **`notification_notificationtemplate`** — удалена; шаблоны теперь файлы в `templates/notification/`.

### Поле в `users_userprofile`

- **`head_of_departments`** — ArrayField. Отдельный маркер headship (НЕ совпадает с `main_departments`, который означает "основной отдел юзера"). Заведено в [crm/users/0005_userprofile_head_of_departments.py](../users/migrations/0005_userprofile_head_of_departments.py). Этот маркер использует `recipients.dep_heads_or_admins` для резолва получателей.

### Env переменные

В `.env` / `settings.py` добавлены / переименованы:
- `EMAIL_BACKEND` (env-управляем, default smtp, для dev можно `console`)
- `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` (стандартные Django-имена)
- `DEFAULT_FROM_EMAIL` (с fallback на `EMAIL_HOST_USER`)

## 5. Информационная безопасность (ISO 27001)

- **Append-only лог.** `Notification` и `EmailNotification` в админке read-only — нельзя добавлять, изменять или удалять через UI. Защита от подделки истории.
- **Логирование SMTP-исключений** в `EmailNotification.status_reason` (текст ошибки) и `logger.exception(...)`. Исключения не пробрасываются в вызывающий код → SMTP-инцидент не валит бизнес-операцию, но остаётся в БД и логах для расследования.
- **Изоляция получателей.** Резолв через `head_of_departments` гарантирует, что письмо о Req отдела X не уйдёт на dep_head'а отдела Y. Fallback на админов — явное и аудируемое поведение.
- **Защита от перекрёстных уведомлений в review-флоу.** В `request_review_action` инициатор запроса исключается из получателей (юзер не пингует сам себя). Если он единственный кандидат — surface ошибка вместо пустой отправки.
- **Email клиента в логе.** В `EmailNotification.recipient_email` хранится email клиента в открытом виде. Не считается чувствительными данными (это адрес отправки), но при удалении клиента не очищается каскадом — лог переживает удаление, что и нужно для аудита.
- **CSRF.** Все POST-эндпоинты (`/mail/document/`, `/mail/freeform/`, `/request-review/`, `/notifications/<pk>/read/`, `/notifications/read-all/`) проходят стандартную CSRF-проверку. Для mark-read в шаблоне используется JS-перехватчик: anchor с `data-mark-read` конвертируется в POST с CSRF-токеном при клике, что не даёт совершать `mark_read` через простой GET.
- **mark_read recipient check.** `inapp_service.mark_read(notification, by_user=...)` сравнивает `recipient_id` с `by_user.id` — чужие уведомления нельзя пометить даже спецально подобранным pk. View дублирует проверку и отдаёт 403.

## 6. Матрица прав доступа

Сейчас триггеры нотификаций **не покрыты явными permissions** — позже эти эндпоинты будут защищены пермишенами (см. план в [DOCS/rbac.md](../../DOCS/rbac.md)). Дефолтное поведение по дизайну:

| Действие / триггер | Кто инициирует | Кто получает |
| :--- | :--- | :--- |
| Сайтовая форма → стафф | анонимный посетитель (через `views.email_template`) | dep_head'ы (Req.depts) → admins |
| Валидация Null → RequestMain | admin (через "Approve" в админке RequestNull) | dep_head'ы (Req.depts) → admins |
| Кнопка "Send mail" → стаффу | любой staff с доступом к change-форме | dep_head'ы (Req.depts) → admins |
| Кнопка "Send mail" → клиенту (freeform) | любой staff с доступом к change-форме | клиент (`request_main.email`) |
| Документ → `in_progress` (signal) | сохранение Oferta/Zlecenie/Wniosek с новым статусом | клиент (`document.email` → `parent.email`) |
| `RequestMain.status` change (signal) | сохранение RequestMain | inapp dep_head'ам (Req.depts) → admins |
| Кнопка "Request review" | любой staff с доступом к change-форме (планируется → specialist) | inapp dep_head'ам (Req.depts) → admins, **исключая инициатора** |

Будущие пермишены (см. матрицу в [DOCS/rbac.md §5](../../DOCS/rbac.md#5-матрица-прав-целевая-черновик)):
- `send_documents` — кнопки "Send mail".
- `request_review` — кнопка "Request review".
- `resolve_review` — закрытие review (триггер ещё не реализован).

## 7. Инструкция для мануального тестирования

Подразумевается, что в БД есть хотя бы один admin (`profile.role.code = "admin"` ИЛИ `is_superuser=True`) с непустым `email`. Иначе все mail-сценарии тихо скипнутся с warning'ом в логе (`notification.mail: skipping send, no recipients`).

### Сценарий 1 — Сайтовая форма → стафф (mail)
1. Без логина перейти на `/zetom/email/`.
2. Заполнить форму валидными данными (имя, телефон, email, компания).
3. Отправить.
4. **Ожидаемый результат:** редирект на админку этой записи; в `mail.outbox` (или реальной почте admin'а) приходит письмо с темой `New request from the site REQ-2026-XXXX (Company)`.

### Сценарий 2 — Валидация Null → стафф (mail)
1. В админке зайти в `/admin/zetom/requestnull/<id>/change/`, нажать "Approve".
2. **Ожидаемый результат:** создаётся RequestMain; admin'у/dep_head'у приходит письмо `Request validated, ready to start REQ-2026-XXXX`.

### Сценарий 3 — Документ → `in_progress` → клиент (mail, signal)
1. В админке создать Oferta для существующего RequestMain.
2. Перевести её статус на `in_progress`, сохранить.
3. **Ожидаемый результат:** клиенту на `oferta.email` (или `parent.email` как fallback) приходит письмо `OFR-2026-XXXX: ваш оферта принят в работу`. Запись об этом — в `/admin/notification/emailnotification/` со статусом `SENT`.

### Сценарий 4 — "Send mail" → стафф по документу
1. В админке `RequestMain.change_form` открыть карточку "Actions" → "Send mail" → "Open".
2. В модалке: Document → выбрать Oferta из списка → "Send to staff".
3. **Ожидаемый результат:** редирект с success-сообщением "Mail sent. Document moved to waiting"; статус документа переключается `in_progress → waiting`; в `EmailNotification` появляется запись со статусом `SENT`.

### Сценарий 5 — "Send mail" → клиент freeform
1. В той же модалке "Actions" → Free message → ввести subject + body → "Send to client".
2. **Ожидаемый результат:** клиенту на `request_main.email` приходит письмо ровно с тем subject/body, что были введены. Запись в `EmailNotification` со статусом `SENT`.

### Сценарий 6 — "Request review" → inapp dep_head'у
1. От имени specialist'а (или любого юзера, не являющегося admin'ом этого отдела) открыть `RequestMain.change_form`.
2. Actions → "Request review" → ввести комментарий → "Send request".
3. **Ожидаемый результат:** редирект с success-сообщением; в шапке у dep_head'а (или admin'а как fallback) увеличивается красный кружок-счётчик на аватаре; в `/admin/notification/notification/?recipient__id__exact=<head_id>&is_read__exact=0` появляется запись `kind=REVIEW_REQUEST` с текстом комментария в payload.

### Сценарий 7 — Inapp при смене статуса RequestMain
1. В `RequestMain.change_form` сменить статус (например, `active → open`), сохранить.
2. **Ожидаемый результат:** у dep_head'ов отделов этого Req создаётся `Notification(kind=STATUS_CHANGE)`; счётчик в шапке обновляется на следующем GET.

### Сценарий 8 — Inbox и mark-read
1. Открыть `/notifications/` (через ACCOUNT-dropdown или sidebar → Inbox).
2. **Ожидаемый результат:** видна страница с заголовком "Notifications", pill "N NEW", сегмент-фильтры "All / Unread", chip-фильтры по `kind`, day-grouping заголовки (Today / Yesterday / Earlier this week), карточки-уведомления. Непрочитанные с зелёной полоской слева и dot'ом справа.
3. Кликнуть по title непрочитанного.
4. **Ожидаемый результат:** редирект на target-объект (например `/admin/zetom/requestmain/<pk>/change/`); запись помечена `is_read=True`, `read_at` заполнен; красный кружок на аватаре в шапке уменьшился на 1.
5. Вернуться в inbox, нажать "Mark all as read" (если есть непрочитанные).
6. **Ожидаемый результат:** все записи стали прочитанными, pill "NEW" пропал, кружок на аватаре исчез.
7. Попробовать GET-ом дёрнуть `/notifications/<pk>/read/` напрямую (без CSRF).
8. **Ожидаемый результат:** 405 Method Not Allowed (POST-only endpoint).
9. От лица другого юзера попробовать POST на `/notifications/<чужой_pk>/read/`.
10. **Ожидаемый результат:** 403 Forbidden — `recipient_id != by_user.id`.

### Что проверять в логах
- `notification.mail: skipping send, no recipients (subject=..., template=...)` — нет ни одного валидного получателя. Чинить через `_admins()` query — должен быть юзер с `is_superuser=True` или `role.code="admin"` и непустым email.
- `notification.mail: failed to send to <email>` + traceback — SMTP-фейл. Смотреть `EmailNotification.status_reason` в админке для деталей.
- `notification.inapp: unknown kind ... — defaulting to SYSTEM` — кто-то вызвал `create_inapp` с неподдерживаемым kind. Чинить вызывающий код.

---

### Чек-лист перед созданием Pull Request:
- [x] Выполнен `git checkout -b django/test` (текущая рабочая ветка).
- [x] Конфликты разрешены локально.
- [x] Создан MD-файл документации модуля (этот файл).
- [x] Использован ИИ — Claude. Помеченные блоки `# claude` в коде написаны им. Промпты вёл Tymur.
