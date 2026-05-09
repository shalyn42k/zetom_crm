# Manual status override for RequestMain — deferred

> **Status:** _deferred — see "Decision (2026-05)" at the bottom._

Когда пользователь меняет статус заявки (`RequestMain`) вручную через Apply
в change-view, сейчас следующий же `handle_child_change` (любая смена статуса
ребёнка) вызывает `update_parent`, который пересчитывает `parent.status` из
детей и **затирает ручной выбор**. Защищены только `cancelled` / `deleted`.

## Желаемое поведение (если будем делать)

- **Manual change > children logic** до тех пор пока не появится **новый** child.
- Появление нового child'а (Oferta / Zlecenie / Wniosek) — снимает блокировку,
  `update_parent` пересчитывает свежий статус.

## Что нужно сделать (если возьмёмся)

1. **`crm/zetom/models.py`** — добавить на `RequestMain`:
   ```python
   manual_status = models.BooleanField(default=False)
   ```
   + `python manage.py makemigrations zetom`.

2. **`crm/zetom/services/status_orchestration.py`** — в `apply_status_change`
   после успешной смены статуса (во всех ветках, включая reason-required):
   ```python
   obj.manual_status = True
   obj.save(update_fields=["manual_status"])
   ```

3. **`crm/zetom/services/request_service.py`** — в `_approve_child`
   после создания child:
   ```python
   main_obj.manual_status = False
   main_obj.save(update_fields=["manual_status"])
   ```
   (выполнить **до** `update_parent(main_obj)`, чтобы пересчёт побежал).

4. **`crm/status_manager/services/status_service.py` (territory другого
   разработчика)** — в `update_parent`, в начале функции, после ранней
   проверки на cancelled/deleted:
   ```python
   if getattr(parent, "manual_status", False):
       return
   ```

## Открытые вопросы (если возьмёмся)

- **Удаление child'а** (`post_softdelete` сейчас зовёт `update_parent`).
  Сбрасывать ли `manual_status` тоже, или оставить блокировку? По умолчанию
  **не сбрасывать** (логика «новый child = новое событие, удаление — нет»).
- **Координация с дев-ом status_manager** — пункт 4 это +1 строка в их
  файле. Решить: правишь сам или передаёшь как тикет/требование.

---

## Decision (2026-05) — _deferred_

После ручных тестов (см. ниже) подтверждено: дыра реальна. Manual `closed` /
`inactive` затираются child-логикой. Несмотря на это **флаг сейчас не
внедряем** по двум причинам:

1. **`inactive` запланирован к сносу** — он семантически дублирует `active`
   (оба = «заявка существует, работы пока нет»). После удаления `inactive`
   из `RequestStatus` останется одна реальная дыра — `closed`.
2. **`closed` is a derived status** — по бизнес-логике parent закрывается
   когда все child-документы завершены (`status=done`). Ручной `closed` без
   этого условия — спорный кейс. Если staff реально хочет «закрыть заявку
   независимо от детей», у него уже есть `cancelled` для этого.

То есть после сноса `inactive` единственное что флаг закрывал бы — это
сценарий «закрыть руками заявку с незакрытыми документами», который пока
не подтверждён как реальное продуктовое требование.

### Когда вернуться к этому

- Если staff в проде начнёт жаловаться «я ставлю Closed, оно само возвращается».
- Если появится бизнес-кейс, где manual `closed` должен быть sticky.

В этот момент: реализовать по 4-пунктовому плану выше.

### Воспроизведение дыры (manual test)

Для контроля что текущая защита работает, и для подтверждения дыры:

**Тест 1 — `cancelled` защищён ✓**
1. Заявка с одним Oferta. Apply→Cancelled с reason → parent = cancelled.
2. У Oferta меняем статус → save.
3. Parent остаётся `cancelled`. ✓

**Тест 2 — `closed` НЕ защищён ✗**
1. Заявка с одним Oferta. Apply→Closed (свободный переход) → parent = closed.
2. У Oferta меняем статус → save.
3. Parent становится `open`. ✗ (дыра подтверждена)

Аналогично для `inactive` — но он на снос, тест неактуален.

### Связанная задача — снос `inactive`

Перед возвратом к этому файлу разобраться с `inactive`:

- Убрать значение из `RequestStatus` enum (`crm/status_manager/services/statuses.py`).
- В `update_parent` no-children ветке: `parent.status = RequestStatus.active`
  (вместо `inactive`).
- Миграция: `RequestMain.objects.filter(status="inactive").update(status="active")`.
- Убрать `inactive` из `REASON_REQUIRED_STATUSES` (`status_orchestration.py`).
- Убрать `inactive_request` функцию там же.
- В CSS `requestmain_detail.css` подчистить `.rm-status-pill--inactive` /
  `.rm-dot--inactive` / `.rm-status-btn--inactive` (мёртвые после сноса).
