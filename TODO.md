# TODO

Общий список того, что нужно сделать/доделать по проекту.
Формат: `- [ ] заголовок` — открытая задача. Закрытые удаляются.
Под пунктом — короткий контекст (1–3 строки), если он не очевиден из заголовка.

---

## Zetom: баги и дыры в правах

- [ ] Свести два пути удаления RequestMain в один
  - `apply_status_change` зовёт `delete_request`, а та сама делает `.delete()` — но оркестратор после этого вызывает `.delete()` ещё раз ([status_orchestration.py:56-58](crm/zetom/services/status_orchestration.py#L56-L58)).
  - Параллельно `delete_model` идёт через `_flip_to_deleted` с reason="Deleted via admin" — без формы причины. Семантика рассинхронизирована.

- [ ] `StatusHistory` создавать ДО `.delete()` в `delete_request` ([status_service.py:104-117](crm/status_manager/services/status_service.py#L104-L117))
  - Сейчас порядок: save → delete → history. На soft-delete пока работает, любая правка каскадов сломает.

- [ ] Проверки прав и `get_object_or_404` в кастомных POST-вью RequestMainAdmin
  - `apply_status_action`, `assign_user_action`, `unassign_user_action`, `add_department_action`, `remove_department_action`, `oferta/zlecenie/wniosek_action` ([requestmain.py:239-350](crm/zetom/admin/requestmain.py#L239-L350)) проверяют только метод POST.
  - Спец с правом `view_requests` может менять департаменты/назначения. `RequestMain.objects.get(...)` бросает 500 на мусорный id.

- [ ] Применить `visible_requests_for` в архивных админах
  - `CancelledRequestAdmin` и `DeletedRequestAdmin` переопределяют `get_queryset` целиком и теряют фильтр видимости — специалист видит чужие департаменты.

- [ ] `views.email_template` редиректит публичного юзера в админку
  - [views.py:25](crm/zetom/views.py#L25) — `redirect("admin:zetom_requestnull_change", ...)`. Анонимный юзер с сайта упирается в логин. Нужен thank-you page.

## Zetom: рефакторинг

- [ ] Объединить `CancelledRequestAdmin` и `DeletedRequestAdmin` в общий `BaseArchiveAdmin`
  - Дублируются `list_display`, `readonly_fields`, `fields`, скрытие save-кнопок, restore-логика. Заодно решит задачу с `visible_requests_for`.

- [ ] Переделать `save_child_with_status` — убрать рефетч ради отката статуса
  - [status_service.py:79-80](crm/status_manager/services/status_service.py#L79-L80) — `type(obj).objects.get(pk=obj.pk).status`. Лучше исключить `status` из формы детей или валидировать без лишнего SQL.

- [ ] DRY для `_partials/documents.html` — три почти одинаковых блока (oferta/zlecenie/wniosek)
  - Включать один шаблон с параметрами (`items`, `url_name`, `create_url`, `prefix`).

- [ ] Вынести кнопки assign/unassign/add-dept/remove-dept из главной формы
  - Сейчас они сабмитят основную форму через `formaction` — конфликтует с `warn_unsaved_form=True`. Сделать отдельные мини-`<form>` или HTMX-AJAX.

- [ ] Перенести `import crm.status_manager.signals` из `ZetomConfig.ready` в `StatusManagerConfig.ready`
  - [apps.py:11-13](crm/zetom/apps.py#L11-L13) — чужие сигналы цепляются «случайно» через zetom.

- [ ] Унифицировать стиль save() для смены статуса (либо везде `update_fields`, либо везде полный save)
  - Сейчас `_flip_to_deleted` использует `update_fields=["status"]`, остальные функции — полный save.

- [ ] Вынести placeholder `"Long and very interesting note … intresting text"` в константу
  - Повторяется в [forms.py](crm/zetom/forms.py) несколько раз, ещё и с опечаткой `intresting`.

- [ ] Ленивый поиск (autocomplete по вводу) для Client и Assigned users в форме RequestMain
  - Сейчас `{{ form.client }}` в [client_card.html:26](crm/zetom/templates/admin/zetom/requestmain/_partials/client_card.html#L26) и `<select name="user_id">` в [assigned_users.html:44-48](crm/zetom/templates/admin/zetom/requestmain/_partials/assigned_users.html#L44-L48) — обычные `<select>` со всеми записями. Departments не трогаем — оставляем дропдаун.
  - План: два JSON-эндпоинта в `RequestMainAdmin` (`clients/search/?q=`, `users/search/?q=&request=<pk>` с исключением уже назначенных), лимит ~20. На фронте — общий Alpine-комбобокс (Alpine уже подключён в `assigned_users.html`): input с дебаунсом, выпадашка, скрытый id-инпут.
  - Открытые вопросы: формат строки для клиента (`Company — NIP …`?), что показывать для юзера кроме ФИО, исключать ли назначенных, нужна ли пагинация при скролле.

- [ ] Решить, нужен ли FSM-переход обратно в `Status.new` для детей
  - В [status_service.py:23-28](crm/status_manager/services/status_service.py#L23-L28) ни один из переходов не ведёт в `new` — статус становится недостижим после первой смены.

- [ ] Подумать про `visible_requests_for` для юзеров без `profile.role`
  - Возвращает `qs.none()` — для `RequestNull` это значит, что свежие заявки с сайта может никто не увидеть.

---

## Admin: User change-page (header-tabs)

- [ ] HTMX-переключение табов на странице `/admin/auth/user/<id>/change/`
  - Сейчас табы переключаются через перезагрузку (`?tab=…`). HTMX даст подмену панели без перезагрузки страницы.
  - Требует эндпоинта-фрагмента в `crm/users/views.py` + URL — зона авторов `users`, согласовать.
  - Аддитивно к текущей реализации, ничего ломать не нужно.

- [ ] Notifications-таб: подключить к реальной модели
  - Сейчас — UI-заглушка, toggles без save'а.
  - Нужна модель (например, `UserProfile.notification_settings` или отдельный `NotificationPreference`) — зона авторов `users`/`notification`.

- [ ] Avatar в шапке профиля
  - Сейчас — инициалы. Хотим загружаемое изображение → нужно поле `UserProfile.avatar = ImageField(...)` и миграция.
  - Зона авторов `users`.

- [ ] Phone в Profile-табе
  - В спеке handoff было, но поля в `UserProfile` нет.
  - Добавить `phone = PhoneNumberField(...)` (или `CharField`) + миграция, потом вывести в Profile.

- [ ] Счётчики у табов (Permissions: 12, Departments: 1 и т.п.)
  - Косметика. Считается из `role.permissions.count()` и т.д. Передать в контекст из админ-view.

- [ ] `INPUT_CLASS` в [crm/users/forms.py:8](crm/users/forms.py#L8) хардкодит тёмные Tailwind-классы (`bg-gray-900 text-white`)
  - Сейчас перебиваем своим CSS на странице User change-form, но в светлой теме это хрупко.
  - Заменить на theme-aware (`bg-white dark:bg-gray-900 text-gray-900 dark:text-white`) или убрать background/color вообще, оставив только layout-классы.
  - Зона авторов `users`.

---

## Notification

### Mail-направление (готово)

- [x] `services/recipients.py` — `dep_heads_or_admins(req)` + `*_emails(req)`.
- [x] `services/mail_service.py` — `send_to_client` / `send_to_staff` с логом в `EmailNotification`. Убран `STAFF_RECIPIENTS` (статическая константа адресов) — получателей всегда резолвит `recipients.py` под конкретный кейс.
- [x] `services/request_mail.py` — `send_document_to_staff`, `send_document_to_client`, `send_freeform_to_client`.
- [x] `services/notification_service.py` — рефакторнут; имена сохранены, хардкод `tymirapps@gmail.com` ушёл.
- [x] `zetom/admin/requestmain_mail.py` — `RequestMailMixin` подключён к `RequestMainAdmin`; два POST-эндпоинта (`/mail/document/`, `/mail/freeform/`).
- [x] Шаблоны `mail/staff/request_new.txt`, `mail/staff/request_validated.txt`.

### Матрица: триггер → канал → получатели

| # | Триггер | Канал | Получатели | Шаблон | Статус |
|---|---|---|---|---|---|
| 1 | Сайтовая форма → `RequestNull` | mail | dep_heads(Req.depts) → admins | `mail/staff/request_new.txt` | done |
| 2 | Null валидирован → `RequestMain` | mail | dep_heads(Req.depts) → admins | `mail/staff/request_validated.txt` | done |
| 3 | Document → `in_progress` (signal) | mail | client (`document.email` → `parent.email`) | `mail/client_in_progress.txt` | done |
| 4 | "Mail" по document (staff action) | mail | dep_heads(Req.depts) → admins | `mail/{oferta,zlecenie,wniosek}_staff.txt` | done |
| 5 | Freeform mail (staff action) | mail | client (`request_main.email`) | — (raw subject/body) | done |
| 6 | Req stale (cron) | mail | dep_heads(Req.depts) → admins | `mail/staff/request_stale_reminder.txt` | pending |
| 6.1 | Req stale + `NOTIFICATION_REMIND_TO_CLIENT` | mail | client | `mail/client/request_stale_reminder.txt` | pending |
| 7 | RequestMain `status` changed | inapp | dep_heads(Req.depts) → admins (assigned specialists позже) | `inapp/staff/request_status_changed.txt` | done |
| 8 | Specialist назначен на Req | inapp | назначенный specialist | `inapp/staff/request_assigned.txt` | pending |
| 9 | Specialist запросил review | inapp | dep_heads(Req.depts) → admins | `inapp/staff/review_requested.txt` | pending |
| 10 | Review resolved | inapp | автор запроса (specialist) | `inapp/staff/review_resolved.txt` | pending |
| 11 | Req cancelled / deleted | inapp | dep_heads(Req.depts) + assigned specialists | тот же `request_status_changed.txt` | pending |
| 12 | Document deleted | inapp | dep_heads(Req.depts) → admins | `inapp/staff/request_status_changed.txt` (или новый kind) | pending |

Правила резолва "→":
- "X → Y" значит "сначала X; если пусто — Y".
- "X + Y" значит "и X, и Y вместе (после де-дупа)".
- "client" определяется по полю `email` на самом объекте (с fallback на родителя для дочек).

### Расширение `recipients.py`

Сейчас один публичный резолвер `dep_heads_or_admins`. По матрице выше нужны ещё:

- [ ] `assigned_specialists(req) -> list[User]` — все `assigned_to` со статусом active. Для триггеров #7, #8, #10, #11.
- [ ] `users_with_role(code) -> list[User]` — `Role.code == code`, `is_active=True`. Для review-флоу: например, "resolvers" = `users_with_role("department_head")` + `users_with_role("admin")`. Базовый кирпич для будущих сценариев.
- [ ] `notify_set_for_status_change(req) -> list[User]` — композитная функция: dep_heads(Req.depts) + admins + assigned_specialists, через `set()` чтобы не дублировать. Триггер #7.
- [ ] *(опционально)* `recipients_for(req, *, include_dep_heads=True, include_specialists=False, include_admins_fallback=True) -> list[User]` — универсальный сборщик. Делать только когда наберём 3+ композитных вариантов и появится реальная польза от унификации.

Под каждый новый резолвер — `*_emails` обёртка для mail-канала.

### Косметика для users-таба (мелочи после head-разделения)

- [ ] CSS для `.up-badge--head` (рендерится как голый текст без стилей).
- [ ] Иконка кнопки grant/revoke head — заменить `♛` на SVG/lucide.

### Inapp-направление (готово)

- [x] `services/inapp_service.py` — `create_inapp(kind, template_name, payload, recipients, actor=None, target=None)`. Один `Notification` на получателя, GFK на `target`.
- [x] Inapp-шаблоны в `templates/notification/inapp/staff/`: `request_status_changed.txt`, `request_assigned.txt`, `review_requested.txt`, `review_resolved.txt`.
- [x] `signals.py` — два связки в одном файле:
  - Документы (Oferta/Zlecenie/Wniosek) → `in_progress` → mail клиенту.
  - RequestMain → смена `status` → inapp dep_heads(Req.depts) + fallback админы. `actor` пробрасывается через `instance._actor` из view.
  - Подключено в `apps.py.ready()`.
- [x] `notification/admin.py` переписан под новые поля. Записи read-only (защита от ручной правки лога).
- [x] Счётчик непрочитанных в ACCOUNT-dropdown (Unfold). Title "Notifications (N)", link на кастомный inbox.
- [x] Кастомная inbox-страница `/notifications/` по handoff V1:
  - filter All/Unread, kind-chips, day-grouping, пагинация 10/страница;
  - клик помечает прочитанным и редиректит на target (`get_absolute_url()` или admin change-view fallback);
  - "Mark all as read" — bulk POST;
  - admin shell (Unfold sidebar/topbar) через `admin.site.each_context(request)`;
  - доступ только `staff_member_required`.
- [x] Триггер `request_review` — кнопка в Actions-card RequestMain, POST `/request-review/`, исключение автора из получателей.
- [x] Sidebar restructure (Inbox / Requests / Archive / Clients / Users & Access / System) + `list_per_page = 10` на Req-чейнджлистах + Notification/EmailNotification.

#### Inapp: что осталось

- [ ] Сигнал на M2M `RequestMain.assigned_to.add(user)` → inapp `request_assigned` для добавленного юзера.
  - Через `m2m_changed`, фильтр `action == "post_add"`. На каждый pk из `pk_set` — отдельная запись.

- [ ] Триггер `resolve_review` — UI-кнопка в RequestMainAdmin для dep_head/admin'а
  - POST endpoint, входит decision (approved/rejected) и note. Создаёт inapp `kind=REVIEW_RESOLVED` на автора оригинального запроса. Триггер покрыт пермишеном `resolve_review` из [DOCS/rbac.md](DOCS/rbac.md).

- [ ] V3 — bell-popover для quick-triage (см. handoff §V3). Сейчас inbox-страница это полноценная V1, popover-вариант отдельной задачей.

### Шаблоны: реорг и напоминания

- [ ] Перетасовать существующие письма
  - `client_in_progress.txt` → `mail/client/document_in_progress.txt` (обновить путь в `request_mail.CLIENT_IN_PROGRESS_TEMPLATE`).
  - Три `*_staff.txt` (oferta/zlecenie/wniosek) → объединить в `mail/staff/document_outgoing.txt` с веткой по `document_kind` (обновить `request_mail._STAFF_TEMPLATE`).

- [ ] Reminder-шаблоны
  - `mail/staff/request_stale_reminder.txt` — напоминание стафу.
  - `mail/client/request_stale_reminder.txt` — клиенту, по флагу `NOTIFICATION_REMIND_TO_CLIENT`.

### Settings и напоминания

- [ ] `settings.py`:
  - `NOTIFICATION_STALE_AFTER = timedelta(...)` — через сколько Req считается залежавшимся.
  - `NOTIFICATION_REMIND_TO_CLIENT = False`.

- [ ] Management-команда `python manage.py send_stale_reminders`
  - RequestMain с `updated_at < now - NOTIFICATION_STALE_AFTER` и не в финальных статусах.
  - `mail/staff/request_stale_reminder.txt`; по флагу — и клиенту.

### SMTP в .env

Backend сейчас захардкожен SMTP. План:
- [ ] Сделать `EMAIL_BACKEND` тоже env-управляемым (`os.getenv("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")`). Тогда в dev можно ставить `console.EmailBackend` (письма в stdout) без правки кода.
- [ ] Для реальной отправки заполнить в production-`.env`: `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USE_TLS`, `SMTP_USER`, `SMTP_PASSWORD`. Не коммитить.
- Локально для интеграционного теста — MailHog / Mailtrap; production — Google Workspace / SendGrid / Mailgun.

## RBAC

Полный хендофф вынесен в [DOCS/rbac.md](DOCS/rbac.md) — матрица прав, текущее состояние кода, открытые дизайн-вопросы и план работ для разработчика.

## Прочее

<!-- Сюда добавлять задачи по другим модулям -->
