"""
View'ы для кнопки "Actions → Mail" на форме RequestMain.

Зачем отдельный файл:
    requestmain.py уже большой и плотный. Письма — самостоятельная фича
    с собственным набором валидаций и тремя сценариями. Логичнее держать
    её рядом, но в отдельном модуле; в requestmain.py будет только
    подключение URL'ов в get_urls().

Что должно жить здесь:

    URL'ы (имена должны совпадать с тем, что использует actions_card.html):
        path("<path:object_id>/mail/document/",
             view(self.mail_document_action),
             name="zetom_requestmain_mail_document"),
        path("<path:object_id>/mail/freeform/",
             view(self.mail_freeform_action),
             name="zetom_requestmain_mail_freeform"),

    def mail_document_action(request, object_id)
        POST. Принимает поля:
            kind: "zlecenie" | "oferta" | "wniosek"
            document_id: pk выбранного существующего дочернего документа.
        Шаги:
          1. Валидация: метод POST; kind в множестве трёх; document_id
             принадлежит этому RequestMain и тип совпадает с kind.
          2. Проверка: document.status == Status.in_progress. Иначе —
             messages.error и redirect назад. (Соответствует ТЗ:
             триггер А переводит in_progress -> waiting и не должен
             срабатывать из других статусов.)
          3. notification.services.request_mail.send_document_to_staff(doc)
          4. messages.success.
          5. redirect на change-view RequestMain.

    def mail_freeform_action(request, object_id)
        POST. Принимает поля:
            subject: непустая строка, max ~200.
            body: непустая строка.
        Шаги:
          1. Валидация через лёгкую Django-форму (subject/body, обе
             обязательные). Если форма невалидна — messages.error и
             redirect назад; в попап заводить сложный возврат пока не
             надо.
          2. request_mail.send_freeform_to_client(
                 request_main=obj, subject=..., body=..., from_user=request.user)
          3. messages.success + redirect.

Чего здесь быть НЕ должно:
    - Рендер шаблонов писем — это уровень request_mail.py.
    - send_mail напрямую — только через сервисы notification.

Подключение к админке:
    В RequestMainAdmin.get_urls() добавить два path()'а, указывающих на
    эти методы. Чтобы методы стали методами админки, проще всего сделать
    их обычными функциями в этом файле и подписать в get_urls() как
    view(self.<имя>), импортировав имена в requestmain.py — либо вынести
    в mixin. Решение оставляем за тем, кто будет это писать; UI на любом
    из вариантов работать будет, имена URL'ов одинаковые.
"""
