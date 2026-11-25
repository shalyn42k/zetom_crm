# Zetom CRM

CRM для ZETOM Katowice: заявки клиентов → оферты, zlecenia, wnioski, клиенты и компании, уведомления. Построена на Django-админке с [django-unfold](https://unfoldadmin.com/).

## Важная инфа

**Перед тем как начинать работу, прочитайте:**

1. [Правила контрибутинга](CONTRIBUTING.md)
2. [Пример оформления документации](DOCS/EXAMPLE.md)

**Касательно ИИ**

* Если вы где-то, как-то используете ИИ, пишите где и для чего, чтобы это можно было разобрать отдельно. Код, написанный Claude, помечен комментарием `# claude`.

---

### Структура проекта

В `crm/` лежат приложения:

* **zetom** — основное: заявки (`RequestNull` → окно валидации → `RequestMain`), оферты, zlecenia, wnioski, окно документа, отделы (`Department`), публичная форма `/zetom/email/`
* **clients** — клиенты и компании, поиск компании по NIP (реестр MF VAT), журнал контактов
* **users** — пользователи, роли и RBAC (кто что видит и редактирует), 2FA, календарь активности
* **status_manager** — статусы заявок и документов
* **notification** — уведомления в приложении и по почте, напоминания, запланированные письма

Отделы хранятся в модели `Department` и редактируются в админке («Departments»). Список отделов в коде берите через `department_choices()`, не через старый `DepartmentsVariants` (он остался только для начальной миграции).

---

### Ветки

`feature/...` → **develop** → **test** → **main**

* Всё попадает в `develop`, `test` и `main` только через pull request, нужен 1 approve от другого человека.
* `test` — проверка перед продом, `main` — прод.
* Что проверять при выкатке на `test`: [DOCS/test_plan_release_test.md](DOCS/test_plan_release_test.md).

---

### Запуск

1. Скопировать `.env.example` в `.env` и заполнить.
2. Поднять Postgres через docker (порт `5434`, см. `docker-compose.yml`):
   ```bash
   docker compose up -d
   ```
3. Поставить зависимости (pip или poetry):
   ```bash
   pip install -r requirements.txt
   # или
   poetry install
   ```
4. Миграции, переводы, суперюзер:
   ```bash
   python manage.py migrate
   python manage.py compilemessages -l pl -l en
   python manage.py createsuperuser
   ```
5. Запуск:
   ```bash
   python manage.py runserver
   ```

Админка: `http://127.0.0.1:8000/admin/` (путь задаётся `ADMIN_URL` в `.env`). При первом входе попросит настроить 2FA (приложение-аутентификатор).

Напоминания и запланированные письма шлёт команда `python manage.py create_followup_reminders` (на сервере её гоняет контейнер `scheduler`). Проверить SMTP: `python manage.py check_smtp`.

---

### Переводы (PL + EN)

Весь новый текст оборачивайте в `gettext_lazy` / `{% trans %}`. Перед пушем:

```bash
python manage.py makemessages -l pl -l en --no-obsolete
# перевести новые строки в locale/pl/LC_MESSAGES/django.po
python manage.py compilemessages -l pl -l en
```

В Django-шаблонах `{# … #}` только однострочный, многострочные комментарии через `{% comment %}…{% endcomment %}`.

---

### Тесты

```bash
python manage.py compilemessages -l pl -l en   # i18n-тесты читают .mo
python manage.py test --noinput
```

Точечно: `python manage.py test --noinput crm.zetom`. Без `--parallel` (на Python 3.14 падает) и не запускайте два прогона одновременно — они делят тестовую БД.

---

### Форматирование

Перед пушем:

```bash
isort .
black .
```

---

### Публичная форма и почта

`/zetom/email/` — форма заявки для клиентов (без логина). Заявка попадает в окно валидации с источником «Site».

Чтобы видеть письма локально, поставьте в `.env`:

```
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
```

— письма будут печататься в консоль.

NIP в форме проверяется строго (контрольная сумма), для теста возьмите любой реальный польский NIP.

Сайт клиента https://zetomkatowice.eu (WordPress) пока с CRM не связан — его форма «Kontakt» только шлёт письмо. Варианты связки описаны в [плане проверки](DOCS/test_plan_release_test.md).
