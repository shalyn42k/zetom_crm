# Manual status override for RequestMain — pending

Когда пользователь меняет статус заявки (`RequestMain`) вручную через Apply
в change-view, сейчас следующий же `handle_child_change` (любая смена статуса
ребёнка) вызывает `update_parent`, который пересчитывает `parent.status` из
детей и **затирает ручной выбор**. Защищены только `cancelled` / `deleted`.

## Желаемое поведение

- **Manual change > children logic** до тех пор пока не появится **новый** child.
- Появление нового child'а (Oferta / Zlecenie / Wniosek) — снимает блокировку,
  `update_parent` пересчитывает свежий статус.

## Что нужно сделать

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

## Открытые вопросы (решить перед имплементацией)

- **Удаление child'а** (`post_softdelete` сейчас зовёт `update_parent`).
  Сбрасывать ли `manual_status` тоже, или оставить блокировку? Сейчас не
  определено — по умолчанию **не сбрасывать** (логика «новый child = новое
  событие, удаление — нет»), но проверить в реальном использовании.
- **Координация с дев-ом status_manager** — пункт 4 это +1 строка в их
  файле. Решить: правишь сам или передаёшь как тикет/требование.
