# Zetom CRM

CRM для ZETOM Katowice: заявки клиентов → оферты, zlecenia, wnioski, клиенты и фирмы, журнал контактов, напоминания и уведомления. Построена на Django-админке с [django-unfold](https://unfoldadmin.com/).

**Версия:** 0.8.0 (beta), см. [CHANGELOG.md](CHANGELOG.md).

---

## Что умеет

* **Приём заявок**: публичная форма `/zetom/email/`, форма «Kontakt» сайта клиента (WordPress → `POST /zetom/api/site-request/`), ручное создание.
* **Окно валидации** (`RequestNull`): проверка лида, поиск дублей среди заявок и клиентов, привязка или создание клиента, выбор отделов и ответственных, перевод в заявку (`RequestMain`).
* **Карточка заявки**: данные клиента, команда и отделы, файлы, журнал работы, история изменений полей, запрос ревью, письма клиенту.
* **Документы**: Oferta → Zlecenie → Wniosek с мягкой цепочкой, окно документа с печатью/PDF и отправкой клиенту.
* **Клиенты и фирмы**: единый список «Klienci», карточки человека и фирмы, поиск фирмы по NIP в реестре VAT (MF).
* **Уведомления**: в приложении и по почте, напоминания о контакте, запланированные письма, настройки уведомлений на пользователя.
* **Права (RBAC)**: роли и права из каталога, видимость по отделам, per-заявка владельцы. Матрица: [docs/rbac.md](docs/rbac.md).
* **Интерфейс**: PL/EN, тёмная тема, работает на телефоне.

## Безопасность

* Обязательная 2FA (TOTP + резервные коды) на всех страницах после входа. Браузер можно «запомнить» на 30 дней.
* Защита от перебора паролей (django-axes): блокировка пары логин+IP после 5 ошибок на час. За Cloudflare берётся реальный IP посетителя (`CF-Connecting-IP`).
* Публичная форма: лимит заявок с одного IP в час, лимит числа и размера файлов.
* Файлы заявок отдаются только после логина и проверки прав; HTML/SVG открываются в изолированной песочнице (CSP `sandbox`).
* Защита от одновременного редактирования: если заявку или документ кто-то сохранил после того, как вы его открыли, сохранение не перезапишет чужие правки молча (подробнее в [crm/zetom/admin/concurrency.py](crm/zetom/admin/concurrency.py)).
* В проде (`DEBUG=False`): secure-cookies, HSTS, HTTPS через Cloudflare, админка по секретному пути `ADMIN_URL`.

## Стек

Python 3.13 · Django 5.2 LTS · PostgreSQL 16 · django-unfold · gunicorn + WhiteNoise · Docker Compose · Cloudflare Tunnel.

## Структура

```
config/            настройки, URL, конфиг Unfold (сайдбар)
crm/zetom/         заявки, окно валидации, документы, отделы, публичная форма и API сайта
crm/clients/       клиенты и фирмы, поиск по NIP, журнал контактов
crm/users/         пользователи, роли и права, 2FA, календарь активности
crm/status_manager/ статусы заявок и документов, история статусов
crm/notification/  уведомления, напоминания, почта, планировщик
templates/, static/ общие шаблоны и стили админки
locale/            переводы PL/EN
docs/              бизнес-требования, RBAC, интеграция с WordPress, диаграммы
```

У модулей `zetom`, `users`, `notification`, `status_manager` есть свои README внутри папки.

Отделы хранятся в модели `Department` и редактируются в админке («Departments»). Список отделов в коде берите через `department_choices()`, не через старый `DepartmentsVariants` (он остался только для начальной миграции).

---

## Локальный запуск

1. Скопировать `.env.example` в `.env` и заполнить (комментарии внутри).
2. Поднять Postgres (порт `5434`):
   ```bash
   docker compose up -d db
   ```
3. Зависимости (Python 3.13+):
   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements-dev.txt
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

Админка: `http://127.0.0.1:8000/admin/` (путь задаётся `ADMIN_URL`). При первом входе попросит настроить 2FA (приложение-аутентификатор).

Письма локально удобно печатать в консоль: `EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend` в `.env`. Проверить SMTP: `python manage.py check_smtp`.

Напоминания и запланированные письма шлёт `python manage.py create_followup_reminders`. В dev при `DEBUG=True` это делает фоновый поток `runserver`, в проде контейнер `scheduler`.

---

## Продакшен

Всё поднимается через `docker-compose.prod.yml`: `db` (Postgres), `web` (gunicorn: 3 процесса × 4 потока), `scheduler` (напоминания раз в минуту), `cloudflared` (туннель, HTTPS). Наружу порты не открываются, трафик идёт только через туннель.

1. `.env` на сервере: `DEBUG=False`, свой `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, случайный `ADMIN_URL`, `DB_HOST=db`, `DB_PORT=5432`, SMTP, `CLOUDFLARE_TUNNEL_TOKEN`, при связке с сайтом `SITE_INTAKE_TOKEN`.
2. Деплой: `./deploy.sh` (git pull → сборка → перезапуск). Миграции, `compilemessages` и `collectstatic` выполняет `docker/entrypoint.sh` при старте `web`.
3. Загруженные файлы лежат в volume `media_data`, база в volume `postgres_data_prod`. **Бэкапьте оба**, например:
   ```bash
   docker exec zetom-db pg_dump -U "$DB_USER" "$DB_NAME" | gzip > backup_$(date +%F).sql.gz
   docker run --rm -v zetom_crm_media_data:/m -v "$PWD":/b alpine tar czf /b/media_$(date +%F).tgz -C /m .
   ```

Связка с сайтом клиента zetomkatowice.eu: [docs/site_integration_wordpress.md](docs/site_integration_wordpress.md).

---

## Разработка

### Ветки

`feature/...` → **develop** → **test** → **main**. В `develop`, `test` и `main` только через pull request с 1 approve от другого человека. `test` — проверка перед продом, `main` — прод. Подробно: [CONTRIBUTING.md](CONTRIBUTING.md), шаблон документации модуля: [docs/module_doc_template.md](docs/module_doc_template.md).

Если используете ИИ, пишите где и для чего. Код, написанный Claude, помечен комментарием `# claude`.

### Тесты

```bash
python manage.py compilemessages -l pl -l en   # i18n-тесты читают .mo
python manage.py test --noinput
```

Точечно: `python manage.py test --noinput crm.zetom`. Без `--parallel` (на Python 3.14 падает) и не запускайте два прогона одновременно: они делят тестовую БД.

### Переводы (PL + EN)

Весь новый текст оборачивайте в `gettext_lazy` / `{% trans %}`. Перед пушем:

```bash
python manage.py makemessages -l pl -l en --no-obsolete --ignore=.venv
# перевести новые строки в locale/pl/LC_MESSAGES/django.po
python manage.py compilemessages -l pl -l en
```

В Django-шаблонах `{# … #}` только однострочный, многострочные комментарии через `{% comment %}…{% endcomment %}`.

### Форматирование

```bash
isort .
black .
```

### Зависимости

`requirements.txt` содержит то, что нужно серверу, `requirements-dev.txt` его же плюс линтеры и форматтеры. Версии закреплены точно; обновляйте осознанно и прогоняйте тесты.
