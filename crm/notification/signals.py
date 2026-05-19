"""
Сигналы, связанные с автоотправкой писем.

Зачем этот файл:
    Триггер Б из ТЗ — "когда любой документ (Oferta / Zlecenie / Wniosek)
    переходит в статус in_progress, клиенту уходит письмо". Это поведение
    хочется навесить через Django signals, чтобы view'ы и админка не
    обязаны были помнить о рассылке руками.

Почему сигналы живут в notification, а не в status_manager:
    status_manager/signals.py уже подписан на post_softdelete и отвечает за
    каскадную смену статуса родителя. Это его доменная зона. Рассылка писем
    — это уже notification. Чтобы не мешать кашу, отправку триггерим
    отсюда.

Как должно работать:

    Для каждой модели (Oferta, Zlecenie, Wniosek):

    @receiver(pre_save, sender=Oferta)
    def _capture_old_status(sender, instance, **kwargs):
        # При существующем pk вытаскиваем старый статус из БД и сохраняем
        # его на самом instance во временный атрибут _old_status.
        # Нужно потому, что в post_save мы уже не увидим, "что было до".
        ...

    @receiver(post_save, sender=Oferta)
    def _send_client_on_in_progress(sender, instance, created, **kwargs):
        old = getattr(instance, "_old_status", None)
        if old != instance.status and instance.status == Status.in_progress:
            request_mail.send_document_to_client(instance)

    Те же два ресивера для Zlecenie и Wniosek (либо общий ресивер через
    цикл по моделям при загрузке приложения).

Подключение:
    Чтобы Django подхватил ресиверы, в crm/notification/apps.py нужно
    добавить:
        def ready(self):
            from . import signals  # noqa: F401

    На этом этапе ready() не правим — это сделает тот, кто будет писать
    тело сигналов. Просто оставляем здесь docstring как контракт.

Чего здесь быть НЕ должно:
    - Логики "после отправки стаффу переключить in_progress -> waiting".
      Это синхронная цепочка из view, а не реакция на сохранение. Если
      сделать это сигналом — получим бесконечный цикл (post_save сменит
      статус -> снова post_save -> ...).
    - Любой работы с request/user — у сигналов их нет. Если для письма
      нужен инициатор — он должен прокинуться через сервис из view.
"""
