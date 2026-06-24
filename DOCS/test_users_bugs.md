# Баги — ручное тестирование

## Тестовые пользователи

| Пользователь | Логин | Пароль | Роль |
|---|---|---|---|
| Jakub Majchrzak | Jakub | Jakub123 | Administrator |
| Alan Błażejczyk | Alan | Alan123 | Specialist |
| Edward Makiela | 1 | test1234 | Administrator |

---

## Подтверждённые баги

### ~~БАГ-1 — Departments редактируются без `edit_users`~~ — ИСПРАВЛЕН ✅
- Исправлено в коммите `d85d927` — кнопки теперь требуют `edit_users` на сервере и в UI.

---

### БАГ-2 — Кнопки статусов отображаются у Specialist

| | |
|---|---|
| **Кто** | Alan (Specialist) |
| **Где** | `/admin/zetom/requestmain/<id>/change/` → блок Status |
| **Проблема** | Кнопки New / In Progress / Waiting / Done / Apply видны, но при нажатии ничего не происходит |
| **Ожидается** | Кнопки скрыты или задизейблены без `change_request_status` |

---

### БАГ-3 — Freeform mail отправляется в обход прав и видимости ⚠️

| | |
|---|---|
| **Кто** | Любой staff-пользователь (проверено: Alan — Specialist) |
| **Где** | POST `/admin/zetom/requestmain/<id>/mail/freeform/` |
| **Проблема** | Эндпоинт не проверяет пермишен `send_documents` и не применяет фильтр видимости. Alan не видит заявку 39 в UI — но через DevTools Console отправил письмо клиенту. Сервер вернул `Status: 200` |
| **Ожидается** | 403 если нет `send_documents` или заявка не видна пользователю |
| **Риск** | Любой staff может отправить письмо от имени компании любому клиенту, зная только ID заявки |

**Как воспроизвести** — под Alan в DevTools Console (F12):
```javascript
fetch('/admin/zetom/requestmain/39/mail/freeform/', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/x-www-form-urlencoded',
    'X-CSRFToken': document.cookie.match(/csrftoken=([^;]+)/)[1]
  },
  body: 'subject=test&body=test+message'
}).then(r => console.log('Status:', r.status, r.url))
```

---

### БАГ-4 — Request Review отправляется в обход прав и видимости ⚠️

| | |
|---|---|
| **Кто** | Любой staff-пользователь (проверено: Alan — Specialist) |
| **Где** | POST `/admin/zetom/requestmain/<id>/request-review/` |
| **Проблема** | Эндпоинт не проверяет пермишен `request_review` и не применяет фильтр видимости. Alan не видит заявку 39 в UI — но через DevTools Console отправил review-запрос Jakub'у. Уведомление пришло в Inbox. Сервер вернул `Status: 200` |
| **Ожидается** | 403 если нет `request_review` или заявка не видна пользователю |
| **Риск** | Любой staff может отправить review-уведомление любому пользователю на любую заявку, зная только ID |

**Как воспроизвести** — под Alan в DevTools Console:
```javascript
fetch('/admin/zetom/requestmain/39/request-review/', {method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded','X-CSRFToken':document.cookie.match(/csrftoken=([^;]+)/)[1]},body:'note=test&recipient_ids=19'}).then(r=>console.log('Status:',r.status,r.url))
```

---

## Не баги — так и задумано

| Поведение | Причина |
|---|---|
| Superuser checkbox заблокирован | Стандартный Django: менять `is_superuser` может только другой superuser. Jakub/Edward — Administrators по роли, но не superuser в Django |
| Alan не видит Users & Access и System | У Specialist нет `view_users` / `view_roles` / `view_logs` по умолчанию |
| Alan видит пустой список в Validation Window | Фильтр видимости возвращает пустой queryset для Specialist — у RequestNull нет departments/assigned_to |
| Restore не работает у Alan | Restore требует `change_request_status`, которого у Specialist нет |
| Jakub не в списке Assign | Owner (Specialist) может назначать только Specialists. Jakub — Administrator, не подходит |
| Alan видит заявки чужого отдела | Specialist видит заявки где его отдел совпадает с отделом заявки — это правильная логика видимости |
