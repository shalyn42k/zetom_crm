# Notification UI — brief

Дизайн и реализация UI для inapp-уведомлений (`Notification` модель в `crm/notification/`). Письма (`EmailNotification`) — отдельная история, тут не трогаем.

---

## 1. Что уже работает

- Запись создаётся через `crm.notification.services.inapp_service.create_inapp(...)` на каждого получателя.
- В шапке (Unfold sidebar, нижний user-widget) уже есть красный кружок-бейдж с числом непрочитанных — поверх аватара. См. [templates/unfold/helpers/navigation_user.html](../templates/unfold/helpers/navigation_user.html).
- В ACCOUNT-dropdown'е есть пункт "Notifications (N)" — линк на `/admin/notification/notification/?recipient__id__exact=<me>&is_read__exact=0`. Сейчас это просто Django admin changelist — функционально, но визуально не то.
- Счётчик пересчитывается через context-processor `crm.notification.context_processors.unread_notifications` на каждом запросе. Запрос индексирован — `(recipient, is_read)`.

## 2. Что нужно сделать дизайнеру/имплементатору

Кастомная страница inbox под URL'ом отдельно от админ-changelist'а. Плюс механика "клик → прочитано".

### 2.1. Внешний вид

- Список уведомлений, отсортирован `-created_at`.
- Непрочитанные визуально выделены (фон чуть светлее/тёмный акцент слева, жирный текст, бейдж "new").
- Прочитанные приглушены.
- В шапке списка — переключатель "Все / Непрочитанные" + кнопка "Mark all as read".
- Для каждой записи:
  - Иконка по `kind` (status_change / review_request / review_resolved / assignment / system) — разные цвета/иконки.
  - **Title** — первая строка отрендеренного шаблона.
  - **Body** — остальные строки (max 2-3 строки в свёрнутом виде, "развернуть" опционально).
  - Время `created_at` ("5 минут назад").
  - Аватар инициатора (`actor`) — если есть.
  - Линк на target (если есть GFK) — например для `kind=status_change` → переход на `RequestMain.change_view`.

Стилистически — в духе того что уже есть: `rm-card` / `up-card` / Tailwind utilities Unfold-а. Цветовая палитра — из [config/unfold_config.py](../config/unfold_config.py) (`COLORS.primary` зелёная).

### 2.2. Механика "клик → прочитано"

- При клике на уведомление (заголовок/тело/линк) — POST на endpoint `mark-read` → переход на target.
- Запрос помечает `is_read=True`, `read_at=now()` через `update_fields=["is_read", "read_at"]`.
- После update сразу делает 302 redirect на URL target'а (если есть GFK) или на change-страницу `Notification` (fallback).
- Endpoint:
  ```
  POST /notifications/<pk>/read/  →  302 target_url
  ```
  Дополнительно может принимать query-параметр `?back=/some/url/` для возврата откуда пришли (если target нет).

Можно ещё:
- "Mark as read" без перехода — отдельная кнопка на каждом item'е (POST `/notifications/<pk>/read/?back=...`).
- "Mark all as read" — POST на `/notifications/read-all/`.

### 2.3. Где жить пейджу

Не админ-changelist. Свой URL вне `/admin/...` (например `/notifications/`) — это даст полную свободу шаблону. Хотя если хочется оставаться внутри Unfold UI, можно делать через кастомное admin-view (как `requestmain.change_form.html`), но это сложнее.

Рекомендую обычный Django view + URL под `/notifications/`, шаблон расширяет `admin/base_site.html` для сохранения хедера/сайдбара Unfold.

---

## 3. Что использовать в коде

### 3.1. Модель `crm/notification/models.py::Notification`

| Поле | Тип | Что значит |
|---|---|---|
| `recipient` | FK `User` | Кому пришло |
| `actor` | FK `User`, nullable | Кто инициировал (для system — None) |
| `kind` | `NotificationKind` | `STATUS_CHANGE`, `REVIEW_REQUEST`, `REVIEW_RESOLVED`, `ASSIGNMENT`, `SYSTEM` |
| `template_name` | `CharField` | Путь к .txt шаблону, рендерится **лениво** на стороне UI |
| `payload` | `JSONField` | Самодостаточный контекст для шаблона (id, имена, лейблы) |
| `target_content_type` + `target_object_id` + `target` (GFK) | — | На какой объект ссылается (RequestMain / Oferta / etc.) |
| `is_read` | `BooleanField` | По умолчанию False |
| `read_at` | `DateTimeField`, nullable | Заполняется в момент пометки прочитанным |
| `created_at` | auto | — |

Индексы есть: `(recipient, is_read)` для счётчика и `(recipient, -created_at)` для списка — запросы быстрые.

### 3.2. Рендер шаблона

Шаблоны лежат в `crm/notification/templates/notification/inapp/staff/` (например `request_status_changed.txt`). Они **обычные Django-шаблоны** — не markdown. Рендерятся через:

```python
from django.template.loader import render_to_string
rendered = render_to_string(notification.template_name, notification.payload)
```

Первая непустая строка = title, остальное = body. Хелпер уже есть: `crm.notification.services.request_mail._split_subject_body(rendered)`. Можно вынести в публичный модуль если будет нужно из UI.

### 3.3. Резолв target'а

```python
if notification.target_content_type and notification.target_object_id:
    target_obj = notification.target  # GenericForeignKey auto-resolves
    # для линка: target_obj.get_absolute_url() или вручную
    # для RequestMain → /admin/zetom/requestmain/<pk>/change/
```

### 3.4. Endpoint'ы которые надо сделать

- `GET /notifications/` — кастомный inbox, рендерит список (с фильтром "только непрочитанные" и пагинацией).
- `POST /notifications/<pk>/read/` — пометить одно прочитанным, redirect.
- `POST /notifications/read-all/` — пометить все прочитанными для current user.

В сервисном слое (`crm/notification/services/inapp_service.py`) можно добавить:

```python
def mark_read(notification, *, by_user):
    """Помечает прочитанным только если recipient == by_user (security check)."""
def mark_all_read(user):
    """Bulk update Notification.recipient=user, is_read=False → is_read=True."""
```

### 3.5. Существующие визуальные паттерны в проекте

Чтобы не выпадать из общей стилистики:

- **Карточки**: `.rm-card`, `.up-card` — закруглённые блоки с тенью.
- **Бейджи**: `.rm-tag`, `.up-badge`, `.up-badge--primary`. Сейчас есть варианты `--primary`/`--muted`/`--head`.
- **Кнопки**: `.rm-btn`, `.rm-btn--primary`, `.rm-btn--sm`.
- **Списки участников**: `crm/users/templates/admin/auth/user/_partials/tab_departments.html` — пример того, как у нас рендерится список людей с аватарами/тегами. Хороший референс для item-а нотификации.
- **Модалки**: `_partials/actions_card.html` — Alpine + teleport + backdrop. Можно использовать тот же паттерн для "mark all confirm" если потребуется.

CSS-переменные тёмной темы цепляются через `html.dark` (см. [project_unfold_dark_theme.md](../memory/...) в памяти). Bg фоны/тексты надо ловить через эти переменные, не хардкодить hex.

### 3.6. i18n

Все новые тексты сразу через `gettext_lazy as _` в Python и `{% trans %}` в шаблонах. `.po` пока не наполняем — это отдельная задача.

---

## 4. Что НЕ нужно делать сейчас

- Не трогать `EmailNotification` — это лог писем, у него своя админ-страница, его трогаем отдельно.
- Не нужны WebSocket-обновления счётчика — сейчас он пересчитывается на каждом GET-запросе. Достаточно.
- Не нужна группировка по типу/дате — простой плоский список с переключателем "все/непрочитанные".

---

## 5. Acceptance criteria

1. У юзера есть страница `/notifications/` со списком его уведомлений.
2. Непрочитанные выделены, прочитанные приглушены.
3. Клик по уведомлению → помечается прочитанным + редирект на target (или на change-страницу Req, или на change-страницу самого уведомления как fallback).
4. Кнопка "Mark all as read" — массово помечает.
5. После пометки счётчик красного кружка в сайдбаре уменьшается на следующем запросе (он уже работает через context-processor — ничего лишнего делать не надо).
6. Дизайн консистентен с тем, что уже есть на других страницах (`rm-*`/`up-*` классы, Unfold темизация).
