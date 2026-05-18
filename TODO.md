# TODO

Общий список того, что нужно сделать/доделать по проекту.
Формат: `- [ ] заголовок` — открытая задача, `- [x]` — закрытая.
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

## Zetom: мёртвый код

- [ ] Убрать дубль `from crm.status_manager.services.statuses import RequestStatus` в [requestmain.py:27](crm/zetom/admin/requestmain.py#L27)

- [ ] Снести недостижимую ветку `if obj.status == RequestStatus.inactive: raise` в `_inactive_request` ([status_orchestration.py:30-31](crm/zetom/services/status_orchestration.py#L30-L31))
  - До неё не доходит — `apply_status_change` уже отсекает «уже в этом статусе» выше.

- [ ] Упростить `response_change`/`response_add` до безусловного редиректа на change view
  - Ветка `if "_continue" not in request.POST and ...` ([requestmain.py:90-102](crm/zetom/admin/requestmain.py#L90-L102)) всегда True — кнопки `_continue`/`_addanother` в шаблоне скрыты.

- [ ] Убрать неиспользуемый `from django.db.models.signals import post_delete` в [signals.py:1](crm/status_manager/signals.py#L1)

- [ ] Убрать `enctype="multipart/form-data"` из формы в [change_form.html:75](crm/zetom/templates/admin/zetom/requestmain/change_form.html#L75) — файловых полей нет

- [ ] `client_autofill.js` грузится дважды
  - Один раз из `Media` в админе, второй раз вручную в [change_form.html:103](crm/zetom/templates/admin/zetom/requestmain/change_form.html#L103) (с другим путём, возможно битым). Оставить только `Media`.

- [ ] Удалить устаревший комментарий в [client_card.html:2-7](crm/zetom/templates/admin/zetom/requestmain/_partials/client_card.html#L2-L7)
  - Текст про «Placeholder for the future Client model» — `ClientField` уже подключён через `TemplateForm`.

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

- [x] Редактируемые `is_active`, `is_staff`, `is_superuser` в Permissions-табе
  - 2026-05-18: добавлено в `CustomUserChangeForm.Meta.fields`, рендерится чекбоксами на Permissions-табе.

---

## Прочее

<!-- Сюда добавлять задачи по другим модулям -->
