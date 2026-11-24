# Requests: меньше кнопок, всё через существующие логи

**Статус:** макеты утверждены 2026-10-27 (https://claude.ai/artifact/PQtRqTC8ktdpK2bvww2qYC)
**Модули:** `zetom`, `notification` (свои), точечно `users`, `clients` (чужие)

## Зачем

Страницы Requests перегружены: карточка «Actions» на полстраницы, две карточки под отделы и людей, вложения дважды, история прямо на странице. Вчерашняя панель «Wiadomości i przypomnienia» добавила параллельный механизм рядом с существующим окном напоминаний — это ошибка, её убираем.

Принцип: меньше видимых элементов; каждое действие пишет в лог, который уже есть.

| Действие | Лог |
|---|---|
| правка данных клиента | база клиентов (как сейчас) |
| контакт / напоминание | `StepNote` заявки или документа («Dziennik kontaktów») |
| статус, назначения, отделы, поля | история заявки (`StatusHistory` + история полей) |
| письмо | журнал e-maili |

## Что строим

1. **Окно напоминаний** — существующая модалка `step_notes_modal.html`, новое только:
   «Komu przypomnieć»: Mnie / Współpracownikom / Roli / Klientowi e-mailem + поля под вариант;
   метка «→ кому» и «wysłane» в Zaplanowane / Historia. Доставка в тике `create_followup_reminders`.
   Права: клиенту `send_client_messages`, коллегам `send_staff_messages`, роли `message_roles`.
   Старые записи без адресата ведут себя как раньше (каскад owners → assigned → автор).
2. **Документ (Oferta/Zlecenie/Wniosek)**: сверху маленькие кнопки (← заявка, Dziennik kontaktów,
   Drukuj/PDF, Oznacz jako wykonane, ⋯ Usuń, Zapisz); слева только поля шаблона (+ свёрнутые данные
   клиента на документе); справа лист + «Utwórz dokument» (сохраняет версию файлом в «Pliki»);
   снизу «Pliki i notatki zespołu» — вложения сотрудников.
3. **Заявка (RequestMain)**: сверху кнопки Dziennik kontaktów, Historia, Weryfikacja, Wyślij e-mail,
   ⋯ (Anuluj/Usuń), Zapisz. Слева Klient, Zgłoszenie, Pliki; справа Zespół (люди + отделы), Dokumenty.
   Карточки Actions и History со страницы уходят в кнопки/модалки.

## Убираем

`ScheduledMessage`, панель-композер, его view/URL/админку/«Moje zaplanowane wiadomości».
Остаются: `NotificationPreference`, 4 perm-кода, уведомление о назначении, экранирование шаблонов.

## Вне объёма

Повторяющиеся напоминания; изменения в карточках клиента/фирмы (их модалка остаётся как есть).
