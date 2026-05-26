# TODO

Общий список того, что нужно сделать/доделать по проекту.
Формат: `- [ ] заголовок` — открытая задача. Закрытые удаляются.
Под пунктом — короткий контекст (1–3 строки), если он не очевиден из заголовка.

---

## Security (критические дыры)

- [x] **`CustomUserAdmin` отдавал права кому угодно** — закрыто 2026-05-25.
  - `has_view_permission` / `has_change_permission` / `has_add_permission` / `has_delete_permission` теперь через `user_has_perm` ([user.py](crm/users/admin/user.py)).
  - Safeguards: non-superuser не может `is_superuser=True` (отключено в `get_form`, дроп в `save_model`); non-superuser не может присвоить роль `admin` / `all_seeing`; нельзя менять собственный role; нельзя удалять себя или superuser'а.

- [x] **Анонимный доступ к `/clients/search/` и `/clients/autofill/`** — закрыто 2026-05-25.
  - Раньше эти эндпоинты отвечали без auth — выгрузка базы клиентов любому. Теперь `@login_required` + `user_has_perm("view_clients")`.
  - `ClientAdmin` тоже получил гейты `view_clients` / `edit_clients` / `delete_clients`.

- [x] **`grant_head` теперь permission-driven** — закрыто 2026-05-26.
  - [`_dept_actions._can_grant_head`](crm/users/admin/_dept_actions.py#L78-L84) теперь зовёт `user_has_perm("grant_head")` вместо hardcoded `is_role("admin")`. Админ может делегировать через `extra_permissions` (нужны: `view_users` + `edit_users` + `grant_head`).

- [ ] **POST-эндпоинты `_dept_actions` без `edit_users` гейта** (осталось)
  - [crm/users/admin/_dept_actions.py](crm/users/admin/_dept_actions.py) — `add_department_action`, `remove_department_action`, `promote_department_action`, `demote_department_action` принимают POST без `user_has_perm("edit_users")`. Сейчас защищены только `admin_view`-обёрткой (is_staff) + новым `has_view_permission` на UserAdmin (фактически view_users). Но прямой POST от юзера с `view_users` без `edit_users` всё ещё проходит — надо добавить явный `user_has_perm("edit_users")` в каждой action.

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

- [ ] Вложения для RequestMain и дочерних модалок (oferta/zlecenie/wniosek) + отправка по почте
  - Модель `RequestAttachment` (FK на RequestMain или GFK на parent + children, `FileField`, `uploaded_by`, `uploaded_at`, валидация размера/MIME).
  - UI: загрузка/список/удаление в основной модалке RequestMain и в каждой из дочерних форм.
  - Mail: прицеплять вложения в `send_document_to_*` / `send_freeform_to_client` через `EmailMessage.attach_file`; учесть SMTP-лимит размера и UTF-8 имена.
  - Решить, кому принадлежит файл — RequestMain или конкретному документу (от этого зависит, какие письма его тянут).
  - На альфу не тянем; задел — можно завести только модель+миграцию без UI.

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

- [ ] Notifications-таб: согласовать с бизнесом и подключить к модели
  - Сейчас [tab_notifications.html](crm/users/templates/admin/auth/user/_partials/tab_notifications.html) — UI-заглушка, 3 disabled toggles.
  - **Сначала нужен бизнес-вход**: какие из 12 триггеров матрицы юзер вправе глушить? По каким каналам (inapp / mail / оба)? Без этого модель проектировать рано — текущие 3 toggle'а это домыслы, могут не совпасть с реальными хотелками.
  - Когда categories утверждены: модель `UserProfile.notification_settings = JSONField` (дёшево, гибко) либо отдельная `NotificationPreference(user, kind, channel, enabled)` (нормализованно). На альфу не критично — без preferences инструмент работает корректно (всем отправляется по умолчанию).
  - Зона: согласование — бизнес; модель/UI — `users`-команда; уважение preferences в send-pipeline — `notification` (моя).

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

### Per-Req owners (готово)

- [x] `RequestMain.owners` (M2M) + миграция `0003_requestmain_owners`.
- [x] Каскад в [recipients.py](crm/notification/services/recipients.py) — `default_recipients(req)` идёт owners → dep_heads(Req.depts) → admins. Старые `dep_heads_or_admins*` оставлены aliases.
- [x] Per-Req permission-хелперы — [crm/zetom/services/per_req_perms.py](crm/zetom/services/per_req_perms.py). Иерархия `admin > dep_head-of-Req > owner > specialist`.
- [x] UI назначения owners — кнопка ★/☆ в карточке Assigned users (только admin / dep_head-of-Req). Bейдж Owner по факту, owners сортируются наверх.
- [x] `unassign` снимает owner-флаг (owners ⊆ assigned).
- [x] `resolve_review` теперь доступен и owner'у Req (даже специалисту).
- [x] `request_review` — picker с тремя секциями: "Always notified (owners)" read-only, "Default recipients" пред-выбранные снимаемые, "Additional recipients" добавляемые. Список фильтруется по правилу sender→target.
- [x] Правило `request_review`: specialist шлёт owners + dep_heads + admins; dep_head — только admins; admin — кому угодно.

#### Per-Req owners: что осталось

- [ ] **Прогон тестировщиком** — пройти сценарии ниже на dev-стенде:
  - admin/dep_head-of-Req назначает Owner спецу из assigned → бейдж появляется, спец сортируется наверх.
  - спец-non-owner: кнопки ★/× не видит, картинка read-only.
  - спец-owner: видит ★/× только у других специалистов, не у dep_head/admin.
  - dep_head чужого отдела: на Req не из его отделов — read-only (как обычный юзер).
  - request_review от specialist'а без owners на Req → default = dep_heads(Req.depts) → admins fallback; extras = весь пул минус default; снять можно только default-checkboxes, owners-блок отсутствует.
  - request_review от specialist'а после назначения owner'а → "Always notified" с owner'ом, default-секция пуста, extras = dep_heads + admins.
  - request_review от dep_head'а → default только admins, extras пусто (peer-dep_head'ы недопустимы).
  - resolve_review: спец-owner закрывает ревью на своём Req без role-perm; обычный спец-non-owner кнопку не видит.
  - mail-сценарии (Send mail → document staff, новая заявка с сайта): письмо уходит owner'ам если они есть, иначе dep_head'ам отдела, иначе админам.
  - unassign owner'а: owner-флаг тоже снимается (проверить и в Notification log).

- [ ] Owners на дочерних `Oferta` / `Zlecenie` / `Wniosek`
  - Сейчас owners живёт только на `RequestMain`. После доработки дочерних форм решить: тащить отдельных owners на каждой дочке или наследовать от parent.
  - Если делать — добавить `owners` в `RequestTemplate` или отдельно на каждой модели + миграция + аналогичный UI.

- [x] Интеграция owner-флага с **validation window** — закрыто 2026-05-26.
  - При approve через VW админ сразу выбирает departments + owners в Step 03. Назначение идёт через `_do_approve` в [requestnull_validate.py](crm/zetom/admin/requestnull_validate.py): `assigned_to.set(owners)` + `owners.set(owners)` (owners ⊆ assigned).

- [ ] Удалить backward-compat aliases `dep_heads_or_admins[_emails]` после полного перехода
  - Сейчас остались в [recipients.py:90-97](crm/notification/services/recipients.py#L90-L97) на случай если где-то ещё используется (нашёл только в test_views.py и README).

- [ ] Обновить [crm/notification/README.md](crm/notification/README.md) — описание каскада owners → dep_heads → admins, а не текущий "dep_heads → admins".

- [ ] Поправить упоминание старого имени в [crm/zetom/tests/test_views.py:141](crm/zetom/tests/test_views.py#L141) (комментарий, не код).

### Mail-направление (готово)

- [x] `services/recipients.py` — каскад `default_recipients(req)` (owners → dep_heads → admins), `*_emails(req)` обёртка.
- [x] `services/mail_service.py` — `send_to_client` / `send_to_staff` с логом в `EmailNotification`. Убран `STAFF_RECIPIENTS` (статическая константа адресов) — получателей всегда резолвит `recipients.py` под конкретный кейс.
- [x] `services/request_mail.py` — `send_document_to_staff`, `send_document_to_client`, `send_freeform_to_client`.
- [x] `services/notification_service.py` — рефакторнут; имена сохранены, хардкод `tymirapps@gmail.com` ушёл.
- [x] `zetom/admin/requestmain_mail.py` — `RequestMailMixin` подключён к `RequestMainAdmin`; два POST-эндпоинта (`/mail/document/`, `/mail/freeform/`).
- [x] Шаблоны `mail/staff/request_new.txt`, `mail/staff/request_validated.txt`.

### Матрица: триггер → канал → получатели

| # | Триггер | Канал | Получатели | Шаблон | Статус |
|---|---|---|---|---|---|
| 1 | Сайтовая форма → `RequestNull` | mail | каскад (Null без depts → сразу admins) | `mail/staff/request_new.txt` | done |
| 2 | Null валидирован → `RequestMain` | mail | каскад (на этом этапе owners ещё нет → dep_heads(Req.depts) → admins) | `mail/staff/request_validated.txt` | done |
| 3 | Document → `in_progress` (signal) | mail | client (`document.email` → `parent.email`) | `mail/client_in_progress.txt` | done |
| 4 | "Mail" по document (staff action) | mail | каскад (owners → dep_heads → admins) | `mail/{oferta,zlecenie,wniosek}_staff.txt` | done |
| 5 | Freeform mail (staff action) | mail | client (`request_main.email`) | — (raw subject/body) | done |
| 6 | Req stale (cron) | mail | каскад | `mail/staff/request_stale_reminder.txt` | pending |
| 6.1 | Req stale + `NOTIFICATION_REMIND_TO_CLIENT` | mail | client | `mail/client/request_stale_reminder.txt` | pending |
| 7 | RequestMain `status` changed | inapp | каскад (assigned specialists добавить позже) | `inapp/staff/request_status_changed.txt` | done |
| 8 | Specialist назначен на Req | inapp | назначенный specialist | `inapp/staff/request_assigned.txt` | pending |
| 9 | Specialist запросил review | inapp | picker: default по каскаду + extras из dep_heads/admins (фильтр по роли отправителя) | `inapp/staff/review_requested.txt` | done |
| 10 | Review resolved | inapp | автор запроса (specialist) | `inapp/staff/review_resolved.txt` | done |
| 11 | Req cancelled / deleted | inapp | каскад + assigned specialists | тот же `request_status_changed.txt` | pending |
| 12 | Document deleted | inapp | каскад | `inapp/staff/request_status_changed.txt` (или новый kind) | pending |

Правила резолва:
- **«каскад»** = `services/recipients.default_recipients(req)`: owners → dep_heads(Req.depts) → admins. Останавливаемся на первом непустом уровне.
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
- [x] Триггер `request_review` — кнопка + picker в Actions-card RequestMain, POST `/request-review/`, role-фильтр sender→target, owners read-only.
- [x] Триггер `resolve_review` — кнопка/модалка в Actions-card. Доступна dep_head/admin'у И owner'у Req. Шлёт `REVIEW_RESOLVED` автору исходного запроса.
- [x] Sidebar restructure (Inbox / Requests / Archive / Clients / Users & Access / System) + `list_per_page = 10` на Req-чейнджлистах + Notification/EmailNotification.

#### Inapp: что осталось

- [ ] Сигнал на M2M `RequestMain.assigned_to.add(user)` → inapp `request_assigned` для добавленного юзера.
  - Через `m2m_changed`, фильтр `action == "post_add"`. На каждый pk из `pk_set` — отдельная запись.

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

### Что добавлено / переосмыслено в матрице (2026-05-25 — 26)

Новые permissions (с реальными гейтами в коде):

| Код | Назначение | Гейт |
|---|---|---|
| `manage_owners` | Set/unset owner на Req | [per_req_perms.can_manage_owners](crm/zetom/services/per_req_perms.py) — admin / dep_head-of-Req получают автоматически; permission даёт делегирование через `extra_permissions`. |
| `view_inbox` | Открыть `/notifications/` | [notification/views.py::inbox](crm/notification/views.py) |
| `view_notification_log` | Админ-список Notification (immutable log) | [notification/admin.py::NotificationAdmin](crm/notification/admin.py) |
| `view_email_log` | Админ-список EmailNotification | [notification/admin.py::EmailNotificationAdmin](crm/notification/admin.py) |
| `view_clients` | Списки/детали клиентов + `/clients/search/`, `/clients/autofill/` | [clients/admin.py](crm/clients/admin.py), [clients/views.py](crm/clients/views.py) |
| `edit_clients` | Создание/правка клиентов | [clients/admin.py](crm/clients/admin.py) |
| `delete_clients` | Удаление клиентов | [clients/admin.py](crm/clients/admin.py) |

Переосмыслены / починены:

| Код | Что было | Что стало |
|---|---|---|
| `edit_roles` | Висел как stub — Role admin был принудительно read-only | Теперь = «право присваивать role / individual permissions конкретному юзеру». UserAdmin: без него `role` field disabled, extras checkbox-ы disabled, save_model дропает изменения. |
| `grant_head` | Был permission, но `_can_grant_head` хардкодил `is_role("admin")` | `_dept_actions._can_grant_head` теперь зовёт `user_has_perm("grant_head")`. Делегирование работает. |
| `view_logs` | Был stub — `LogEntryAdmin.has_view_permission` возвращал `True` всем | Теперь = «доступ к Activity Log» (`/admin/admin/logentry/`). По дефолту даётся admin / dep_head / auditor. |

Удалены (мёртвые декорации без UI):
- `view_dashboard`, `view_admin_panel` — нет дашборда; `is_staff` уже гейтит вход в `/admin/`. Удалены из `permissions_data` + auto-cleanup осиротевших Permission-строк в `signals.py`.

Дефолтные роли:
- **admin**: всё (через `[p[0] for p in permissions_data]`).
- **dep_head**: `manage_owners`, `view_inbox`, `view_clients`, `edit_clients` (плюс прежний набор).
- **specialist**: `view_inbox`, `view_clients`, `edit_clients` (нужно для autofill/search в форме Req).
- **auditor**: `view_inbox`, оба `view_*_log`, `view_clients`.

Единственный оставшийся stub — `view_logs` (нет admin-страницы под `StatusHistory`).

### Что в матрице ещё «мёртвое» / не подключено

- [x] ~~`view_admin_panel`, `view_dashboard`~~ — удалены 2026-05-26 (нет UI, мёртвый груз).
- [x] ~~`edit_roles`~~ — переосмыслено 2026-05-26. Permission больше **не** про правку `Role` модели (она остаётся read-only), а про право **присваивать роль / individual permissions конкретному юзеру** в UserAdmin. Без него юзер видит таб Permissions read-only.
- [x] ~~`grant_head` hardcoded~~ — закрыто 2026-05-26 (см. секцию Security).
- [x] ~~`view_logs`~~ — подключено 2026-05-26 к `LogEntryAdmin` (Activity Log). Раньше `has_view_permission` возвращал `True` для всех.

**STUB-список теперь пуст** — все perm-коды в `crm/users/signals.py::permissions_data` имеют рабочий гейт.

### Потенциальные новые permissions (на обсуждение с RBAC-команды)

- [ ] `restore_request` — сейчас `restore_action` в [cancelledrequest.py:69](crm/zetom/admin/cancelledrequest.py#L69) гейтится `change_request_status`. Если хочется отделить «вернуть из архива» от «менять статус», нужен отдельный код. Не критично.
- [ ] `mail_freeform_client` — сейчас freeform-mail к клиенту делает любой с `send_documents`. Если бизнес хочет отделить «свободные письма» от «отправка готового документа» — добавить отдельный код.
- [ ] `validate_null` — для VW; добавить когда дойдём до доработки validation window.

### Видимость для dep_head в visibility.py (DOCS/rbac.md §7.3)

- [ ] `crm/zetom/services/visibility.py:34` — dep_head сейчас видит все Req (как admin). Нужно сузить до `qs.filter(departments__overlap=profile.head_of_departments)`, иначе head ничем не отличается от auditor по видимости.

## Validation Window

Базовая страница реализована по [design_handoff_validation_window/](design_handoff_validation_window/) (commit `feat(zetom): validation window for RequestNull`). Заменяет старую одну кнопку Approve: `change_view` на `RequestNullAdmin` редиректит на `/admin/zetom/requestnull/<id>/validate/` → 3-зонная форма (Snapshot · Link to Client · Assignment) + sticky footer (Cancel / Discard as spam / Approve & create RequestMain). На странице помечено WIP-тегами всё, что ещё не работает.

### VW: что осталось

- [ ] FK `RequestMain → Client` + миграция
  - Сейчас «линковка» в [`_do_approve`](crm/zetom/admin/requestnull_validate.py) копирует поля Client в новый RequestMain, но связь не сохраняется. Когда добавим FK — поменять `_do_approve` на `new_main.client = client` и убрать копирование полей.

- [ ] Live HTMX-фильтрация owners по departments
  - Сейчас `userpop` показывает всех активных юзеров; правило «owners ∈ users-with-overlapping-dept» проверяется в `ValidationWindowForm.clean()` и при несовпадении возвращает форму с ошибкой. Нужен `htmx GET` партиал «users-for-departments» + `hx-trigger=change` на чипах департаментов. WIP-нотис убрать после.

- [ ] Drag-reorder primary owner
  - Сейчас primary = первый выбранный (наименьший pk). По дизайну: первый чип = primary, должна быть возможность переставлять (минимум — действие «make primary», максимум — DnD).

- [ ] Ad-hoc client search box
  - `.search-row` в шаблоне сейчас `disabled` + WIP-тег. План: эндпоинт `clients/search/?q=` (уже есть в [crm/clients/views.py](crm/clients/views.py)) + Alpine-комбобокс над списком кандидатов, чтобы можно было найти клиента, которого матчер не предложил.

- [ ] `validate_null` permission (см. RBAC секцию ниже)
  - Сейчас view защищён только `admin_view`-обёрткой (is_staff). Завести отдельный permission и гейтить `validation_window_view`, `_do_approve`, discard-ветку.

- [ ] Тесты на матчер дубликатов
  - [`crm/zetom/services/duplicate_matcher.py`](crm/zetom/services/duplicate_matcher.py) — score / badges / порядок. Случаи: exact phone, exact email, NIP, similar name (порог 0.78), email domain, пустой результат, weak-only.

- [ ] Notification kind для «discarded as spam»
  - Сейчас при discard создаётся RequestMain и сразу cancel'ится через `cancel_request` — событие пишется в `StatusHistory`, но отдельного inapp-уведомления для админов нет. Решить с RBAC-командой, нужно ли.

## Прочее

<!-- Сюда добавлять задачи по другим модулям -->
