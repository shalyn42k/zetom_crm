# Единая лента контактов и напоминаний + цепочка Oferta → Zlecenie → Wniosek

1. **Статус:** дизайн утверждён, реализация не начата
2. **Автор:** shalyn42k
3. **Дата:** 2026-08-24
4. **Модули:** `zetom`, `clients`, `notification`

---

## 1. Проблема

### 1.1. Две несвязанные ленты контактов

В проекте две модели, описывающие одно и то же событие «мы связались с клиентом»:

| | `zetom.StepNote` | `clients.ClientInteraction` |
|---|---|---|
| Привязка | GenericFK на документ (`RequestMain` / `Oferta` / `Zlecenie` / `Wniosek`) | FK на `Client` + опциональный FK на `RequestMain` |
| Канал связи | нет | `channel` (call/email/meeting/chat/other) |
| Собеседник | нет | `contact_person` (свободный текст) |
| Когда состоялся контакт | нет (только `created_at`) | `contacted_at` |
| Напоминание | `next_contact_at` + `reminder_sent_at` | нет |
| Где видно | модалка «Work log» на карточке документа | панель «Historia kontaktów» на карточках персоны и фирмы (read-only) |

Друг о друге они не знают. Сотрудник, записавший звонок на карточке клиента, не увидит его в ленте заявки, и наоборот. Напоминание можно поставить только со стороны документа.

### 1.2. Напоминание нельзя поставить без разговора

`next_contact_at` — поле внутри `StepNote`, а `text` у `StepNote` обязателен. Чтобы поставить себе напоминание «позвонить 5-го», надо сначала выдумать заметку о разговоре, которого не было.

### 1.3. Документы висят веером, а не цепочкой

`Oferta`, `Zlecenie`, `Wniosek` — три сиблинга на `RequestMain.from_main`, создаются независимо кнопками на карточке заявки. Бизнес-порядок (оферта → злецение → внёсек) нигде не выражен и живёт устным соглашением.

Для сравнения — в legacy-CRM (`zetbase-legacy`, Node/Mongo) порядок был жёстким: `Offer.idInquiries` обязателен, `Order.idOffer` обязателен, а создание злецения авто-закрывало оферту (`offer-controller.js:401 save_order`).

---

## 2. Скоуп

**Входит:**

- `StepNote` становится единственной моделью записи контакта и напоминания
- `ClientInteraction` удаляется, данные мигрируют в `StepNote`
- Напоминание без разговора — через `kind`
- Панели на карточках персоны и фирмы: «Historia kontaktów» становится записываемой, добавляется «Zaplanowane»
- Мягкая цепочка `from_oferta` / `from_zlecenie`
- Модалка Work log переезжает со своих `sn-*` классов на `cc-*` из `clients`

**Не входит (отдельные задачи):**

- Визуальное упрощение формы **Information** (карточка `RequestMain`, классы `rm-*`) — следующая задача после этой
- Модалка «Stwórz zlecenie» с полями по отделам из legacy — требует справочников (курсы, производители, wyroby), которых в базе нет
- Отдельная страница «Мои напоминания» и бейджи «следующий контакт» в списках — сознательно отклонены
- Авто-закрытие `Zlecenie` при создании `Wniosek` — сознательно отклонено

---

## 3. Целевая data-model

### 3.1. `StepNote` — новые и изменённые поля

Добавляются:

| Поле | Тип | Смысл |
|---|---|---|
| `kind` | choices `contact` / `reminder` | тип записи |
| `channel` | choices call/email/meeting/chat/other, `blank=True` | канал связи; пусто у напоминания |
| `contacted_at` | `DateTimeField(null=True)` | когда состоялся разговор — не `created_at` |
| `person` | `FK(clients.Client, null=True, SET_NULL)` | собеседник — персона из базы |
| `contact_person` | `CharField(blank=True)` | фолбэк, если персоны в базе нет |
| `done_at` | `DateTimeField(null=True)` | напоминание закрыто |

Меняются:

- `text` → `blank=True` (у напоминания достаточно `action`)
- `target_content_type` / `target_object_id` → nullable

Остаются без изменений: `author`, `created_at`, `action`, `next_contact_at`, `reminder_sent_at`, `target` (GenericFK).

**Почему `target` становится nullable.** Контакт, записанный с карточки клиента, может не относиться ни к одной заявке. У `ClientInteraction.request` это уже так — мы переносим существующую семантику, а не вводим новую вольность.

**Инварианты** (`clean()` + `CheckConstraint`):

- `kind == contact` ⟹ `contacted_at IS NOT NULL`
- `kind == reminder` ⟹ `next_contact_at IS NOT NULL`

`done_at` осмыслен только при `kind == reminder`; у контактов остаётся `NULL`.

### 3.2. Цепочка документов — мягкая

- `Zlecenie.from_oferta` → `FK(Oferta, null=True, blank=True, on_delete=SET_NULL)`
- `Wniosek.from_zlecenie` → `FK(Zlecenie, null=True, blank=True, on_delete=SET_NULL)`

`from_main` **остаётся заполненным всегда**: при создании из оферты в него копируется `oferta.from_main`. Благодаря этому `BaseRequestAdmin._step_note_targets`, `services/visibility.py` и все существующие запросы работают без правок — новые FK только добавляют информацию, ничего не переносят.

Мягкая, а не жёсткая: создать злецение напрямую с карточки заявки по-прежнему можно (клиент без оферты, срочный случай). Существующие документы-сироты не ломаются.

**Переход статуса.** Создание `Zlecenie` из `Oferta` переводит оферту в `done` — правило перенесено из legacy. Живёт в `crm/zetom/services/status_orchestration.py`. Симметричного правила для `Wniosek` из `Zlecenie` **нет**.

---

## 4. Стратегия миграции данных

`ClientInteraction` → `StepNote`, один-в-один:

```
client         → person
request        → target (GenericFK на RequestMain)
channel        → channel
summary        → text
contacted_by   → author
contact_person → contact_person
contacted_at   → contacted_at
—              → kind = contact
```

Порядок миграций:

1. Добавить поля `StepNote`, сделать `target` nullable, `text` blank — **без** констрейнтов
2. Проставить `kind = contact` всем существующим `StepNote`, `contacted_at = created_at`
3. Скопировать `ClientInteraction` → `StepNote`
4. Навесить `CheckConstraint`
5. Удалить `ClientInteraction`

Констрейнты навешиваются шагом 4, а не 1, иначе шаг 2 не пройдёт на боевых данных.

Данные `ClientInteraction` боевые — шаг 3 не мержится без теста, сверяющего количество и все поля.

---

## 5. Поверхности

### 5.1. Модалка Work log — общая точка записи

`crm/zetom/templates/admin/zetom/shared/step_notes_modal.html`.

Наверху формы переключатель типа:

- **«Zapisz kontakt»** → канал (select), дата разговора, собеседник, что сделано, заметка, дата следующего контакта (опц.)
- **«Zaplanuj przypomnienie»** → дата, что напомнить, заметка (опц.)

Собеседник — select персон из базы, не свободный текст. Источник на странице документа: персоны заявки (`RequestMain.clients`) плюс персоны связанной фирмы (`Company` → `CompanyPersonLink`). Под селектом текстовое поле-фолбэк для «звонил кто-то, кого в базе нет».

Кнопки «+ добавить персону» прямо из модалки (как в legacy `#addPerson`) нет — вместо неё ссылка на карточку клиента. Форма создания персоны не должна жить в двух местах.

### 5.2. Общий бэкенд записи

Сейчас создание заметки — `BaseRequestAdmin.step_note_create_action` (`crm/zetom/admin/base.py:100`). С карточки клиента оно понадобится тоже, поэтому логика выносится в `crm/zetom/services/step_notes.py`: одна функция, оба админа её зовут, валидация инвариантов там же.

Новые endpoints:

- `clients_client_step_note_create` в `ClientAdmin.get_urls` — запись контакта/напоминания с карточки клиента. Гейт `edit_clients`, как у остальных write-контролов карточки
- `zetom_stepnote_done` — проставляет `done_at` напоминанию (кнопка-галочка из §5.3). Гейт — тот же, что у создания заметки на соответствующей поверхности

Оба зовут функции из `services/step_notes.py`, своей логики не содержат.

### 5.3. Карточки персоны и фирмы

`crm/clients/admin.py:523` (персона) и `:724` (фирма).

Панель «Historia kontaktów» перестаёт быть read-only:

- **источник** — `StepNote` с `person=client` (персона) / `person__company_links__company=company` (фирма) вместо `ClientInteraction`; форма строки не меняется, поля уже совпадают
- **кнопка «Dodaj kontakt»** открывает ту же модалку; заявка выбирается из связанных либо не выбирается вовсе
- **новая секция сверху — «Zaplanowane»**: записи `kind=reminder` с пустым `done_at`; просроченные (`next_contact_at < now`) подсвечены; кнопка-галочка проставляет `done_at`

Закрытые напоминания уходят из «Zaplanowane», но остаются в «Historia».

### 5.4. Колокольчик и cron

`crm/notification/services/followup_reminders.py` — одна правка в `_resolve_recipients` (строка 64): сейчас `target is None` возвращает пустой список, то есть заметка без заявки не напомнит никому. Для таких получатель — `author`.

Остальное (`create_followup_reminders`, `inapp_service`, шаблон `followup_due.txt`) не трогаем.

### 5.5. Стиль

В проекте три набора классов: `rm-*` (карточка заявки), `cc-*` (карточки `clients`), `sn-*` (`static/zetom/css/step_notes.css`, только модалка Work log).

`sn-*` устраняется: модалка переписывается на `cc-*`, `step_notes.css` удаляется, `BaseRequestAdmin.Media` начинает грузить `clients/css/company_card.css`. Правила там заскоплены на `.cc-stage`, поэтому модалка заворачивается в один такой div.

Готовые примитивы в `static/clients/css/company_card.css`: таймлайн `.hist/.hev/.dot/.line/.hbody/.hmeta/.htext` (строка 151+), модалка `.overlay/.modal/.modal-h/.modal-b/.modal-f/.modal-x`, Alpine-паттерн как у `mOsobowe`.

Просроченным напоминаниям добавляется модификатор с красной точкой — `.dot` уже параметризован через CSS-переменную.

`rm-*` не трогается: редизайн карточки заявки — следующая задача.

---

## 6. Фазировка

Каждая фаза — рабочий, тестируемый софт.

1. **Данные** — поля `StepNote`, nullable `target`, `done_at`, констрейнты; data-миграция `ClientInteraction` → `StepNote`; удаление `ClientInteraction`, её админки и инлайна
2. **Сервис** — `crm/zetom/services/step_notes.py`, перевод `base.py` на него, фикс `_resolve_recipients`
3. **Цепочка** — `from_oferta` / `from_zlecenie`, кнопки создания на карточках оферты и злецения, авто-закрытие оферты
4. **UI** — модалка на `cc-*`, панели «Historia» и «Zaplanowane» на карточках персоны и фирмы
5. **i18n** — новые строки PL + EN

---

## 7. Тесты

- data-миграция: N `ClientInteraction` → N `StepNote`, поля сходятся один-в-один
- констрейнт: `kind=contact` без `contacted_at` падает
- констрейнт: `kind=reminder` без `next_contact_at` падает
- напоминание без заявки уведомляет автора (регрессия на `_resolve_recipients`)
- существующий `test_followup_reminders_command` остаётся зелёным
- карточки персоны и фирмы рендерят `StepNote` — переписываются `test_company_card_panels`, `test_interaction_admin`, `test_zetom_integration`
- `from_oferta` проставляется при создании из оферты, оферта уходит в `done`
- `done_at` убирает напоминание из «Zaplanowane», но оставляет в «Historia»
- RBAC: пользователь с `view_clients` без `edit_clients` не может POST-ить заметку

Разработка идёт TDD: тест до кода в каждой фазе.

---

## 8. i18n / терминология

Новые строки оборачиваются в `gettext_lazy` / `{% trans %}` и переводятся на PL + EN до закрытия задачи (`makemessages` → перевод → `compilemessages`).

Терминология интерфейса — польская, как на существующих карточках:

| Смысл | PL | EN |
|---|---|---|
| Контакт (запись разговора) | Kontakt | Contact |
| Напоминание | Przypomnienie | Reminder |
| Запланированные напоминания | Zaplanowane | Scheduled |
| История контактов | Historia kontaktów | Contact history |
| Собеседник | Rozmówca | Interlocutor |
| Канал | Kanał | Channel |
| Дата разговора | Data rozmowy | Contact date |
| Следующий контакт | Następny kontakt | Next contact |

---

## 9. Definition of Done

- Все тесты из §7 зелёные
- `ClientInteraction` отсутствует в кодовой базе, боевые данные перенесены и сверены
- Напоминание можно поставить и закрыть с карточки персоны и с карточки документа
- Контакт, записанный на карточке клиента, виден в ленте связанной заявки, и наоборот
- `step_notes.css` удалён, модалка выглядит как остальные модалки `clients`
- Новые строки переведены на PL и EN, `compilemessages` прогнан
- Python-блоки, написанные ассистентом, помечены `# claude`

---

## 10. Открытые / паркованные вопросы

- **Авто-закрытие `Zlecenie` при создании `Wniosek`** — отклонено как дефолт. Вернуться, если окажется, что внёсек всегда идёт после исполнения злецения, а не параллельно ему.
- **Страница «Мои напоминания»** — отклонена. Пока напоминания видны только на карточке персоны и в колокольчике. Вернуться, если сотрудники начнут терять напоминания по клиентам, которых редко открывают.
- **Модалка «Stwórz zlecenie» по отделам** — заблокирована отсутствием справочников. Минимум для отдела szkolenia: модель курса с `symbol` / `title` / `day` / `time` (последние два автозаполняют поля формы). Отделы `DS` / `DC` / `DE` из legacy к нашему `DepartmentsVariants` не сводятся — маппинга нет, нужен отдельный дизайн.
