"""
Высокоуровневые сценарии рассылки, привязанные к RequestMain и его дочкам
(Oferta / Zlecenie / Wniosek).

Зачем этот файл:
    Кнопка "Actions → Mail" из формы RequestMain и автотриггеры из сигналов
    зовут одни и те же функции отсюда. Разница только в источнике вызова.
    Так логика "какой шаблон + куда отправлять + что после этого менять"
    не дублируется между view и signal.

Зависимости:
    - mail_service.send_to_client / send_to_staff — единственный способ
      реально что-то отправить;
    - django.template.loader.render_to_string — рендер .txt шаблонов из
      crm/notification/templates/notification/mail/;
    - crm.zetom.models — только для type-hints; импорт делать локально
      внутри функций, чтобы не плодить циклические импорты при загрузке
      приложений.

Что должно жить здесь:

    def send_document_to_staff(document) -> None
        Используется триггером А (кнопка "Mail" в попапе формы RequestMain,
        когда выбран существующий документ Zlecenie / Oferta / Wniosek).
        Шаги:
          1. По типу document'а выбрать шаблон:
             Zlecenie  -> notification/mail/zlecenie_staff.txt
             Oferta    -> notification/mail/oferta_staff.txt
             Wniosek   -> notification/mail/wniosek_staff.txt
          2. Контекст шаблона: сам document + его from_main.
          3. Отрендерить subject (первая строка шаблона) + body.
          4. mail_service.send_to_staff(...).
          5. Сменить статус документа: in_progress -> waiting.
             Если статус НЕ in_progress — ничего не менять и не отправлять
             (валидация уровня view должна была это поймать, но дублируем
             как защиту).

    def send_document_to_client(document) -> None
        Используется триггером Б (документ перешёл в in_progress).
        Шаги:
          1. Найти email клиента: document.email -> fallback document.from_main.email.
          2. Шаблон: notification/mail/client_in_progress.txt.
             Один шаблон на все три типа, тип документа — переменная
             в контексте, чтобы тело адаптировалось.
          3. mail_service.send_to_client(...).

    def send_freeform_to_client(*, request_main, subject, body, from_user) -> None
        Используется кнопкой "Mail → Freeform" в попапе.
        Шаги:
          1. Адрес: request_main.email.
          2. Никакого шаблона — subject/body берутся как есть из попапа
             (валидация и санитайзинг — на уровне Django формы во view).
          3. mail_service.send_to_client(...).
          4. from_user пока не используется в теле письма, но принимаем его
             на будущее: захотим записать в EmailNotification.user, или
             добавить подпись "Отправлено: <username>".

Что НЕ должно жить здесь:
    - Прямые вызовы send_mail (только через mail_service).
    - Любая работа с request/POST — это уровень view'а в zetom.
    - Транзакции по смене статуса с записью в StatusHistory: смену статуса
      из in_progress -> waiting делаем простым save(update_fields=[...]),
      а уже сигнал из status_manager сам напишет в историю.
"""
