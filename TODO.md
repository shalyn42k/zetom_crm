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

### Косметика для users-таба (мелочи после head-разделения)

- [ ] CSS для `.up-badge--head` (новая бейджка "Head" на странице User → Departments)
  - Сейчас рендерится рядом с `.up-badge--primary`, но стилей нет — выглядит как голый текст.
  - Подобрать цвет, отличный от Primary и Secondary.

- [ ] Иконка кнопки grant/revoke head
  - Сейчас стоит `♛` (Unicode crown). Возможно стоит заменить на SVG/lucide-icon, как остальные кнопки админки.

### Сервисный слой

- [ ] `crm/notification/services/recipients.py` — `dep_heads_or_admins(request_main) -> list[User]`
  - Пересечение `request_main.departments` с маркером headship (см. блокер выше), fallback на админов.
  - Пока поля нет — временная заглушка: всегда возвращает админов.

- [ ] `crm/notification/services/mail_service.py` — `render_and_send_mail(template_name, context, recipients, actor=None)`
  - Рендер через `render_to_string`, первая строка = subject, остальное = body.
  - Создаёт `EmailNotification(status=PENDING)`, шлёт через `send_mail`, при успехе → `SENT` + `sent_at`, при исключении → `FAILED` + `status_reason`. Исключение НЕ пробрасывает (чтобы SMTP-фейл не валил view/сигнал).
  - В `payload` сохранять денормализованную копию контекста (id + ключевые поля), не сериализуемые объекты выкидывать.

- [ ] `crm/notification/services/inapp_service.py` — `create_inapp(kind, template_name, context, recipients, actor=None, target=None)`
  - Создаёт `Notification` на каждого получателя. Если передан `target` — заполняет `target_content_type`/`target_object_id` через `ContentType.objects.get_for_model`.
  - Рендер происходит на стороне UI при выводе, поэтому `payload` должен быть самодостаточен.

- [ ] Рефактор `crm/notification/services/notification_service.py`
  - Существующие `send_notification_to_staff` и `send_notification_approve_null` перевести на `render_and_send_mail` + `recipients.dep_heads_or_admins`.
  - Убрать хардкод `tymirapps@gmail.com`.

### Шаблоны

- [ ] Перетасовать существующие письма в `templates/notification/mail/`
  - `client_in_progress.txt` → `mail/client/document_in_progress.txt`.
  - Три `*_staff.txt` (oferta/zlecenie/wniosek) → объединить в `mail/staff/document_outgoing.txt` с веткой по `document_kind`.

- [ ] Новые mail-шаблоны
  - `mail/staff/request_new.txt` — то, что сейчас делает `send_notification_to_staff` вручную.
  - `mail/staff/request_validated.txt` — то, что сейчас делает `send_notification_approve_null` вручную.
  - `mail/staff/request_stale_reminder.txt` — напоминание стафу о залежавшемся Req.
  - `mail/client/request_stale_reminder.txt` — напоминание клиенту (опционально, по флагу `NOTIFICATION_REMIND_TO_CLIENT`).

- [ ] Inapp-шаблоны в `templates/notification/inapp/staff/`
  - `request_status_changed.txt` — RequestMain сменил `RequestStatus`. Контекст: `request`, `old_status`, `new_status`, `actor`.
  - `request_assigned.txt` — над Req назначили исполнителя (переезд из mail).
  - `review_requested.txt` — specialist дёрнул вышестоящего на проверку. Контекст: `request`, `document?`, `requester`, `target`, `note`.
  - `review_resolved.txt` — ответ ревьюера (`decision`, `note`).

### Сигналы

- [ ] Реализовать тело `crm/notification/signals.py` (там пока только docstring)
  - `pre_save`/`post_save` на Oferta/Zlecenie/Wniosek: при переходе в `Status.in_progress` отправлять `mail/client/document_in_progress.txt`.
  - `pre_save`/`post_save` на RequestMain: при смене `status` создавать inapp `request_status_changed` для dep_head'ов/админов. `actor` пробрасывать через `instance._actor`, выставленный во view (сигнал юзера сам не знает).
  - Подключить `signals` в `apps.py.ready()`.

### Settings и напоминания

- [ ] Добавить в `settings.py`:
  - `NOTIFICATION_STALE_AFTER = timedelta(...)` — через сколько Req считается залежавшимся.
  - `NOTIFICATION_REMIND_TO_CLIENT = False` — слать ли клиенту напоминания.

- [ ] Management-команда `python manage.py send_stale_reminders`
  - Выбирает RequestMain с `updated_at < now - NOTIFICATION_STALE_AFTER` и не в финальных статусах.
  - Шлёт `mail/staff/request_stale_reminder.txt` стафу, по флагу — и клиенту.

### Админка и счётчик

- [ ] Переписать `crm/notification/admin.py` под новые поля
  - `Notification`: показывать `kind`, `recipient`, `template_name`, `is_read`, `created_at`. Фильтр по `kind` и `is_read`.
  - `EmailNotification`: `recipient_email`, `status`, `subject`, `sent_at`. Фильтр по `status`.

- [ ] Счётчик непрочитанных возле ACCOUNT
  - Context processor или middleware: `Notification.objects.filter(recipient=user, is_read=False).count()`.
  - Прокинуть в шаблон шапки Unfold.

- [ ] Кастомная страница inbox для inapp-уведомлений
  - Отдельная вью со списком `Notification` текущего юзера, кнопка "mark all read", переход по `target`.

## RBAC

Полный хендофф вынесен в [DOCS/rbac.md](DOCS/rbac.md) — матрица прав, текущее состояние кода, открытые дизайн-вопросы и план работ для разработчика.

## Прочее

<!-- Сюда добавлять задачи по другим модулям -->
