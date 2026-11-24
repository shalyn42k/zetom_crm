# Security review — 2026-07-02

> Область: полный аудит проекта на уязвимости, отдельный фокус — обход прав в модуле `users`.
> Ветка: `django/test`. Метод: чтение исходников (не только диффа) + трассировка потоков данных.
> Исключено по запросу: отсутствие 2FA и подобные hardening-меры.

Статусы: 🔴 НЕ ИСПРАВЛЕН · 🟡 ЧАСТИЧНО · ✅ ЗАКРЫТ

---

## 🔴 SEC-1 — Неаутентифицированный CRUD пользователей + эскалация до суперюзера

**Severity:** HIGH · **Confidence:** 10/10 · **Категория:** auth_bypass / privilege_escalation

**Файлы:**
- `crm/users/views.py:14-110`
- `crm/users/urls.py:5-12`
- `crm/users/forms.py:97-200`
- `config/urls.py:27`
- `config/settings.py:87-98` (MIDDLEWARE)

### Суть
Все шесть view в `crm/users/views.py` — голые `django.views.View` **без единой проверки прав**:
нет `LoginRequiredMixin`, `@login_required`, `user_has_perm`, `is_staff`/`is_superuser`,
нет object-level проверки владения.

Подключены в корень сайта (`config/urls.py:27` → `path("users/", include("crm.users.urls"))`),
то есть **вне** `/admin/`. Значит `admin_site.admin_view` (который в админке навешивает login+staff) здесь
не срабатывает. Глобального login-middleware нет (`MIDDLEWARE` без `LoginRequiredMiddleware`), `LOGIN_URL` не задан.

Эти view дублируют и обходят весь RBAC, аккуратно навешанный на `CustomUserAdmin`.

CSRF-middleware включён, но не защищает: страница с формой (`GET`) тоже открыта анонимно —
атакующий сначала забирает CSRF-токен, затем шлёт `POST`.

### Открытые маршруты (`crm/users/urls.py`)

| Маршрут | View | Что даёт анониму |
|---|---|---|
| `GET /users/` | `UserListView` | список всех юзеров + профилей |
| `GET/POST /users/create/` | `UserCreateView` | создать юзера с **любой ролью** |
| `GET/POST /users/<pk>/edit/` | `UserEditView` | правка любого юзера, включая `is_superuser` и сброс пароля |
| `POST /users/<pk>/delete/` | `UserDeleteView` | удалить любого юзера |
| `GET /users/<pk>/` | `UserDetailView` | чтение любого профиля |
| `GET/POST /users/me/` | `UserProfileEditView` | правка `request.user` (для анонима упадёт в 500) |

### Формы шире, чем в админке
- `CustomUserCreateForm` (`forms.py:26`): `role = Role.objects.all()` — **без** фильтра
  `PRIVILEGED_ROLE_CODES`, который стоит в админ-форме. Юзер создаётся сразу с админ-ролью.
- `CustomUserChangeForm.Meta.fields` (`forms.py:130-135`) включает `is_active`, `is_staff`,
  **`is_superuser`**, плюс `role` и смену пароля (`new_password1/2`). В отличие от
  `CustomUserAdmin.save_model`, здесь **нет** защит, сбрасывающих `is_superuser` и блокирующих
  привилегированные роли — `form.save()` пишет `is_superuser` напрямую.

### Сценарий атаки
1. `GET /users/create/` → забрать CSRF-токен из формы.
2. `POST /users/create/` с `username=attacker&password=…&password_confirm=…&role=<pk админ-роли>`
   → создаётся `User` + `UserProfile` с админ-ролью. Проверок прав нет.

Либо эскалация существующего аккаунта:
3. `POST /users/<victim_pk>/edit/` с `is_superuser=on` (+ обязательные поля)
   → `is_superuser=True` на любом аккаунте. Тем же путём — сброс пароля любому юзеру.

Итог: полный обход аутентификации, эскалация до суперюзера, захват/удаление любых аккаунтов,
чтение всех профилей.

### Варианты исправления (от лучшего к запасному)
1. **Удалить мёртвый слой.** Похоже, это легаси-дубликат админки — реальный UI юзеров живёт в
   `CustomUserAdmin` под `/admin/`. Убрать `crm/users/views.py`, `crm/users/urls.py` и include
   в `config/urls.py:27`. Предварительно проверить, что на `name=` этих маршрутов никто не ссылается:
   `grep -rn "user_list\|user_create\|user_edit\|user_delete\|user_detail" --include=*.html --include=*.py`.
2. **Если слой нужен — закрыть каждый view.** `LoginRequiredMixin` + проверка
   `user_has_perm(request.user, "view_users"/"edit_users")`. Из форм убрать
   `is_superuser`/`is_staff`/`role` **или** повторить защиты из `save_model`
   (фильтр `PRIVILEGED_ROLE_CODES`, запрет менять свою роль/флаги, форс-сброс `is_superuser`).
   Добавить object-level проверки.
3. **Defense-in-depth.** Глобальный `LoginRequiredMiddleware` (Django 5.1+) с allowlist публичных
   путей (`/zetom/email/`, `/i18n/`) — тогда всё вне `/admin/` требует логина по умолчанию.

---

## Проверено и чисто (не уязвимости)

- **`/zetom/email/`** (`crm/zetom/views.py:32`) — публичная форма приёма заявок с сайта
  (создаёт `RequestNull`, `source=SITE`, без привилегий). Так задумано.
- **`crm/clients/views.py`** — везде `@login_required` + `user_has_perm`; `client_attach_search`
  без декоратора, но смонтирован только через `ClientAdmin.get_urls` → `admin_view` (staff-auth),
  плюс сам проверяет `edit_clients`.
- **`crm/notification/views.py`** — `staff_member_required`/`login_required` + проверка владения
  получателем на `mark_read`.
- **`crm/zetom/services/per_req_perms.py` / `visibility.py`** — иерархия
  `admin > dep_head-of-Req > owner > specialist` корректна; `is_dep_head_of_req` правильно
  ограничивает headship отделами конкретного Req; мутации в `requestmain.py` проверяют это per-object.
- **`CustomUserAdmin`** (`crm/users/admin/user.py`) — защиты от self-эскалации в `save_model`,
  `PRIVILEGED_ROLE_CODES`, заблокированное редактирование своей роли.
- SQL-инъекций нет (везде ORM `Q`/filter). `|safe`/`mark_safe` на недоверенных данных нет
  (единственный `|safe` в `tab_security.html:19` — собственный help-text валидатора паролей Django).
  Нет eval/pickle/YAML-десериализации, command injection, template injection.
  `SECRET_KEY`/креды БД читаются из env, не захардкожены.

**Единственное действие — SEC-1.** Остальная модель прав сделана верно; дыра ровно там, где
параллельный не-админский слой обошёл общую RBAC.
