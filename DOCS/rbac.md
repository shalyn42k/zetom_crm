# RBAC: матрица прав, текущее состояние и план работ

Хендофф для разработчиков, ведущих модуль `users` и матрицу прав. Часть правок затрагивает `zetom/admin/*` — согласовать с автором zetom-модуля.

---

## 1. Контекст

- Permissions объявлены в [crm/users/signals.py:30-40](../crm/users/signals.py#L30-L40), роли — там же в `roles_data` ([signals.py:48-86](../crm/users/signals.py#L48-L86)).
- Проверка — централизованно через `user_has_perm` ([crm/users/utils.py](../crm/users/utils.py)).
- Видимость объектов по ролям — [crm/zetom/services/visibility.py](../crm/zetom/services/visibility.py).
- Бизнес-требования по ролям — [DOCS/requirements.md](requirements.md) §3, §5.

---

## 2. Что уже реализовано в коде

### Модели
- `Role` (с FK на `Permission` через M2M) и `Permission` ([crm/users/models.py:12-26](../crm/users/models.py#L12-L26)).
- `UserProfile.role` — OneToOne связка `User → UserProfile → Role`.
- `UserProfile.departments` (ArrayField) — все отделы юзера.
- `UserProfile.main_departments` (ArrayField, ⊆ departments) — "основные" отделы (НЕ headship).
- `UserProfile.head_of_departments` (ArrayField, ⊆ departments) — явный маркер headship.

### Permissions (9 объявленных, через `post_migrate`-сигнал)
| Code | Где реально проверяется |
|---|---|
| `view_dashboard` | **нигде** (мёртвый) |
| `view_admin_panel` | **нигде** (мёртвый) |
| `view_users` | [users/admin/userprofile.py:14](../crm/users/admin/userprofile.py#L14) |
| `edit_users` | [userprofile.py:17,20,23](../crm/users/admin/userprofile.py#L17) |
| `view_roles` | [users/admin/role.py:13](../crm/users/admin/role.py#L13) |
| `edit_roles` | **нигде** (Role-админ жёстко read-only) |
| `view_requests` | [zetom/admin/base.py:42](../crm/zetom/admin/base.py#L42), [cancelledrequest.py:34](../crm/zetom/admin/cancelledrequest.py#L34), [deletedrequest.py:45](../crm/zetom/admin/deletedrequest.py#L45) |
| `edit_requests` | [zetom/admin/base.py:45,48](../crm/zetom/admin/base.py#L45) |
| `delete_requests` | [zetom/admin/base.py:51](../crm/zetom/admin/base.py#L51) |

### Роли (по умолчанию, из `signals.py::roles_data`)
| Role code | Дефолтные permissions |
|---|---|
| `admin` | все 9 |
| `department_head` | view_dashboard, view_requests, edit_requests, view_users |
| `specialist` | view_dashboard, view_requests, edit_requests |
| `auditor` | view_dashboard, view_requests |
| `all_seeing` | view_dashboard, view_requests, view_users, view_roles |

### Видимость Req
- `specialist` — `assigned_to=user` OR `departments__overlap=profile.departments` ([visibility.py:23-32](../crm/zetom/services/visibility.py#L23-L32)).
- `admin`, `department_head`, `auditor`, `all_seeing` — **видят всё без фильтра** ([visibility.py:34](../crm/zetom/services/visibility.py#L34)).

### Headship-эндпоинты (новое)
- HTMX-эндпоинты `grant_head`/`revoke_head` в [users/admin/_dept_actions.py](../crm/users/admin/_dept_actions.py).
- **Закрыты хардкодом `_can_grant_head`** (superuser ИЛИ `role.code == "admin"`), а не через `user_has_perm`. Это технический долг, см. план работ ниже.

### Тесты
- Шаблон с моком `user_has_perm` через `@patch(..., side_effect=always_true)` — [zetom/tests/test_admin.py:36](../crm/zetom/tests/test_admin.py#L36).

---

## 3. Чего ещё нет в коде (важно для тестов)

Эти куски ТЗ ещё не покрыты — нет смысла писать на них тесты сейчас, нужно сначала реализовать.

### Permissions не объявлены
Из требований (`requirements.md` §3, §5) недостают:
- `view_logs` — доступ к логам.
- `change_request_status` — смена статуса Req (отдельно от `edit_requests`).
- `send_documents` — отправка писем по oferta/zlecenie/wniosek.
- `assign_requests` — назначение/снятие исполнителей.
- `grant_head` — назначение/снятие headship по отделу.
- `request_review` — specialist дёргает вышестоящего на проверку.
- `resolve_review` — вышестоящий разрешает review.

### POST-эндпоинты идут без проверок прав
Сейчас опираются только на `request.method`. Любой залогиненный со ссылкой на админку может их дёрнуть.

**[crm/zetom/admin/requestmain.py](../crm/zetom/admin/requestmain.py)** — 8 actions:
| Endpoint | Строка |
|---|---|
| `add_department_action` | [:234](../crm/zetom/admin/requestmain.py#L234) |
| `remove_department_action` | [:253](../crm/zetom/admin/requestmain.py#L253) |
| `assign_user_action` | [:267](../crm/zetom/admin/requestmain.py#L267) |
| `unassign_user_action` | [:286](../crm/zetom/admin/requestmain.py#L286) |
| `apply_status_action` | [:303](../crm/zetom/admin/requestmain.py#L303) |
| `oferta_action` | [:332](../crm/zetom/admin/requestmain.py#L332) |
| `zlecenie_action` | [:337](../crm/zetom/admin/requestmain.py#L337) |
| `wniosek_action` | [:342](../crm/zetom/admin/requestmain.py#L342) |

Заодно `RequestMain.objects.get(pk=...)` нужно поменять на `get_object_or_404` — иначе мусорный id даёт 500.

**[crm/users/admin/_dept_actions.py](../crm/users/admin/_dept_actions.py)** — 6 actions: `add`, `remove`, `promote`, `demote`, `grant_head`, `revoke_head`. Сейчас опираются на доступ к change-page (а grant/revoke — на хардкод `_can_grant_head`).

### Видимость department_head не реализована
В [visibility.py:34](../crm/zetom/services/visibility.py#L34) dep_head видит все Req — должен видеть только те, чьи `departments` пересекаются с его `head_of_departments`.

### "Custom"-роль (all_seeing) — нет механики
Сейчас `Role.permissions` общие для всех с этой ролью. User-specific overrides и автофлип в `all_seeing` при отклонении от дефолта — это отдельный архитектурный кусок, см. §6.

### Auditor read-only тест-режим — не реализован
`requirements.md §3.3` определяет "Тестовый просмотр": auditor видит интерфейс, но действия фактически не выполняются. Сейчас auditor просто не имеет действующих permissions — кнопки скрыты `has_*_permission`-проверками, но "видеть кнопку, нажать, ничего не произошло" не реализовано.

### Логирование (Полный/Частичный/Инцидентный) — не реализовано
`requirements.md §3.2` определяет три уровня логов как `Immutable`. Соответствующих моделей и пайплайнов нет. Permission `view_logs` тоже не объявлен.

### Тесты с `always_false`
Сейчас тестов на "юзер без permission → 403" нет — есть только мок `always_true`, проверяющий, что под админом всё работает.

---

## 4. Модель ролей

- **all_seeing — это "custom"-роль.** Дефолт у неё пустой. Когда admin изменяет набор прав конкретного юзера, отличный от дефолта его роли, этот юзер автоматом становится `all_seeing` с теми правами, что admin ему выдал. Любая комбинация прав допустима. (См. §6 — механики "user-specific overrides + flip to all_seeing" пока нет.)
- **auditor — view-only ("тестовый просмотр")**. В `requirements.md` у auditor стоит `[x]` почти везде, но это видимость интерфейса в read-only-режиме, не реальная возможность мутировать. В permissions-матрице auditor получает только `view_*`. Сам режим test-read-only ещё не реализован.
- **Кто может грантить permission** — отдельное измерение. Важные пермишены (затрагивают целостность пользователей, ролей, удаление и headship) выдаёт только admin. Менее важные (по работе с Req: документы, статусы, назначения) может выдавать также dep_head.

---

## 5. Матрица прав (целевая, черновик)

Легенда: ✓ — есть право, пусто — нет. Колонка **all_seeing** заведомо пустая (по дефолту), заполняется admin'ом для конкретного юзера.

| Permission | admin | dep_head | specialist | auditor | all_seeing | Грантит |
|---|:---:|:---:|:---:|:---:|:---:|:---|
| `view_dashboard` | ✓ | ✓ | ✓ | ✓ |   | admin |
| `view_admin_panel` | ✓ |   |   | ✓ |   | admin |
| `view_users` | ✓ | ✓ |   | ✓ |   | admin |
| `edit_users` | ✓ |   |   |   |   | **admin only** |
| `view_roles` | ✓ |   |   | ✓ |   | admin |
| `edit_roles` | ✓ |   |   |   |   | **admin only** |
| `view_requests` | ✓ | ✓ | ✓ | ✓ |   | admin |
| `edit_requests` | ✓ | ✓ | ✓ |   |   | admin / dep_head |
| `delete_requests` | ✓ | ✓ |   |   |   | **admin only** |
| `view_logs` *(new)* | ✓ | ✓ |   | ✓ |   | admin |
| `change_request_status` *(new)* | ✓ | ✓ |   |   |   | admin / dep_head |
| `send_documents` *(new)* | ✓ | ✓ | ✓ |   |   | admin / dep_head |
| `assign_requests` *(new)* | ✓ | ✓ | ⚠ |   |   | admin / dep_head |
| `grant_head` *(new)* | ✓ |   |   |   |   | **admin only** |
| `request_review` *(new)* |   |   | ✓ |   |   | admin / dep_head |
| `resolve_review` *(new)* | ✓ | ✓ |   |   |   | admin / dep_head |

Спорные места:
- `assign_requests` для specialist (⚠) — в `requirements.md §5` у спеца стоит `[x]` в "Назначение", но в `§3.3` сказано "Назначать могут только пользователи выше по иерархии". Противоречие в ТЗ. Решить: спец вообще не назначает, или назначает только себе.

---

## 6. Открытые дизайн-вопросы

### "Custom"-роль (all_seeing) — как технически реализовать
Сейчас `Role.permissions` общие для всех с ролью. Нет user-specific overrides. Варианты:
- **(а)** добавить `UserProfile.extra_permissions = M2M(Permission)` и `UserProfile.role` оставить ролевым шаблоном — при наличии extras проставлять `role=all_seeing` через `save()`;
- **(б)** сделать `Role` per-user (один Role на одного юзера для all_seeing'ов) — не масштабируется;
- **(в)** гибрид: один общий `all_seeing` Role, но проверка `user_has_perm` смотрит ещё и в `UserProfile.extra_permissions`.

Рекомендуется (а) или (в). Решить и заложить в `user_has_perm`, чтобы не размазывать логику.

### "Кто может грантить" — отдельный механизм
Нужно отделять "permissions, видимые в форме грантера" от "всех permissions в системе". Сейчас этого нет — UI редактирования Role жёстко выключен ([crm/users/admin/role.py:15-22](../crm/users/admin/role.py#L15-L22)).

---

## 7. План работ

### 7.1. Завести новые permissions

Добавить в [crm/users/signals.py::permissions_data](../crm/users/signals.py#L30):
- `view_logs` — "View logs"
- `change_request_status` — "Change request status"
- `send_documents` — "Send document emails (oferta/zlecenie/wniosek)"
- `assign_requests` — "Assign/unassign users to requests"
- `grant_head` — "Grant/revoke department head"
- `request_review` — "Request review from a higher role"
- `resolve_review` — "Resolve review (approve/reject)"

И раздать по `roles_data` согласно матрице §5.

### 7.2. Закрыть дыры в POST-эндпоинтах

**[crm/zetom/admin/requestmain.py](../crm/zetom/admin/requestmain.py)** — навесить `user_has_perm`:

| Endpoint | Строка | Нужный permission |
|---|---|---|
| `add_department_action` | [:234](../crm/zetom/admin/requestmain.py#L234) | `edit_requests` |
| `remove_department_action` | [:253](../crm/zetom/admin/requestmain.py#L253) | `edit_requests` |
| `assign_user_action` | [:267](../crm/zetom/admin/requestmain.py#L267) | `assign_requests` |
| `unassign_user_action` | [:286](../crm/zetom/admin/requestmain.py#L286) | `assign_requests` |
| `apply_status_action` | [:303](../crm/zetom/admin/requestmain.py#L303) | `change_request_status` |
| `oferta_action` | [:332](../crm/zetom/admin/requestmain.py#L332) | `send_documents` |
| `zlecenie_action` | [:337](../crm/zetom/admin/requestmain.py#L337) | `send_documents` |
| `wniosek_action` | [:342](../crm/zetom/admin/requestmain.py#L342) | `send_documents` |

Заодно: `RequestMain.objects.get(pk=...)` → `get_object_or_404(RequestMain, pk=...)`.

**[crm/users/admin/_dept_actions.py](../crm/users/admin/_dept_actions.py):**

| Endpoint | Нужный permission |
|---|---|
| `add_department_action`, `remove_department_action`, `promote_department_action`, `demote_department_action` | `edit_users` |
| `grant_head_department_action`, `revoke_head_department_action` | `grant_head` (заменить хардкодный `_can_grant_head` на проверку через `user_has_perm`) |

### 7.3. Починить видимость для department_head

[crm/zetom/services/visibility.py:34](../crm/zetom/services/visibility.py#L34) — сейчас admin, dep_head, auditor, all_seeing видят все Req. Для dep_head нужно сузить:

```
elif profile.is_role("department_head") and profile.head_of_departments:
    return qs.filter(departments__overlap=profile.head_of_departments).distinct()
```

(точная форма — на усмотрение разраба). Иначе head ничем не отличается от auditor по видимости.

### 7.4. Решить судьбу мёртвых permissions

Нигде не проверяются:
- `view_dashboard` ([signals.py:31](../crm/users/signals.py#L31)) — подключить (например, в дашборде Unfold) или удалить из `permissions_data`.
- `view_admin_panel` — то же.
- `edit_roles` — Role-админ жёстко read-only ([role.py:15-22](../crm/users/admin/role.py#L15-L22)). Либо разрешить редактирование под этим permission, либо удалить.

### 7.5. Тесты

Покрыть каждый из задействованных endpoint'ов парой кейсов: "юзер с permission → 200" / "юзер без permission → 403".

Шаблон уже есть: [zetom/tests/test_admin.py:36](../crm/zetom/tests/test_admin.py#L36) использует `@patch("...user_has_perm", side_effect=always_true)`. По аналогии можно сделать `always_false` и проверить 403.
