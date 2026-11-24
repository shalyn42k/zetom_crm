# ──────────────────────────────────────────────────────────────────────────────
# ТЕСТЫ СЕРВИСОВ (status_manager.services.status_service)
#
# Что тут тестируется:
#   • change_status — FSM-переходы для дочерних документов
#   • update_parent — обновление статуса RequestMain по состоянию детей
#   • handle_child_change — атомарная операция: смена статуса ребёнка + обновление родителя
#   • save_child_with_status — обёртка для admin.save_model
#   • cancel_request / delete_request — смена статуса родительской заявки
#
# Почему тут MagicMock:
#   save_child_with_status принимает request и messages_module — нам не нужна
#   реальная HTTP-заявка или модуль messages, достаточно объекта с нужными методами.
# ──────────────────────────────────────────────────────────────────────────────

from unittest.mock import MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase

from crm.status_manager.models import StatusHistory
from crm.status_manager.services.status_service import (
    cancel_request,
    change_status,
    delete_request,
    handle_child_change,
    save_child_with_status,
    update_parent,
)
from crm.status_manager.services.statuses import RequestStatus, Status
from crm.zetom.models import Oferta, RequestMain, Wniosek, Zlecenie

User = get_user_model()

BASE_DATA = {
    "phone": "+48501600300",
    "email": "contact@zetom.pl",
}


# ────────────────────────── change_status ─────────────────────────────────────

class ChangeStatusTests(TestCase):
    """FSM-переходы дочернего документа (Oferta/Zlecenie/Wniosek).

    Разрешённые переходы:
        new → in_progress → waiting → done
        done → waiting | in_progress  (возврат к работе)
    Всё остальное — ValueError.
    """

    def setUp(self):
        main = RequestMain.objects.create(**BASE_DATA)
        self.oferta = Oferta.objects.create(**BASE_DATA, from_main=main)

    def test_new_to_in_progress_allowed(self):
        change_status(self.oferta, Status.in_progress, reason=None, user=None)
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.status, Status.in_progress)

    def test_in_progress_to_waiting_allowed(self):
        self.oferta.status = Status.in_progress
        self.oferta.save()
        change_status(self.oferta, Status.waiting, reason=None, user=None)
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.status, Status.waiting)

    def test_waiting_to_done_allowed(self):
        self.oferta.status = Status.waiting
        self.oferta.save()
        change_status(self.oferta, Status.done, reason=None, user=None)
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.status, Status.done)

    def test_done_to_in_progress_allowed(self):
        # Возврат к работе — разрешён (например, обнаружили ошибку)
        self.oferta.status = Status.done
        self.oferta.save()
        change_status(self.oferta, Status.in_progress, reason=None, user=None)
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.status, Status.in_progress)

    def test_done_to_waiting_allowed(self):
        self.oferta.status = Status.done
        self.oferta.save()
        change_status(self.oferta, Status.waiting, reason=None, user=None)
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.status, Status.waiting)

    def test_illegal_transition_new_to_waiting_raises(self):
        # new → waiting — прыжок через шаг. Должен бросить ValueError.
        with self.assertRaises(ValueError):
            change_status(self.oferta, Status.waiting, reason=None, user=None)

    def test_illegal_transition_new_to_done_raises(self):
        with self.assertRaises(ValueError):
            change_status(self.oferta, Status.done, reason=None, user=None)

    def test_same_status_is_silent_noop(self):
        # Переход в тот же статус — ничего не делает, не бросает исключение.
        change_status(self.oferta, Status.new, reason=None, user=None)
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.status, Status.new)

    def test_none_status_is_silent_noop(self):
        # None означает «не менять» — ранний return в функции.
        change_status(self.oferta, None, reason=None, user=None)
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.status, Status.new)


# ────────────────────────── update_parent ─────────────────────────────────────

class UpdateParentTests(TestCase):
    """Логика вычисления статуса RequestMain по состоянию детей.

    Правила:
        нет детей                       → active
        есть дети, хоть один in_progress или waiting → open
        все три типа (oferta+zlecenie+wniosek) и все done → closed
        иначе (есть дети, все new или done, но не все типы) → active
        cancelled/deleted родитель       → без изменений (ранний return)
    """

    def setUp(self):
        self.main = RequestMain.objects.create(**BASE_DATA)

    def test_no_children_sets_active(self):
        update_parent(self.main)
        self.main.refresh_from_db()
        self.assertEqual(self.main.status, RequestStatus.active)

    def test_in_progress_child_sets_open(self):
        Oferta.objects.create(**BASE_DATA, from_main=self.main, status=Status.in_progress)
        update_parent(self.main)
        self.main.refresh_from_db()
        self.assertEqual(self.main.status, RequestStatus.open)

    def test_waiting_child_sets_open(self):
        Oferta.objects.create(**BASE_DATA, from_main=self.main, status=Status.waiting)
        update_parent(self.main)
        self.main.refresh_from_db()
        self.assertEqual(self.main.status, RequestStatus.open)

    def test_all_three_types_all_done_sets_closed(self):
        # Закрытие только когда есть ВСЕ три типа документов и все done.
        Oferta.objects.create(**BASE_DATA, from_main=self.main, status=Status.done)
        Zlecenie.objects.create(**BASE_DATA, from_main=self.main, status=Status.done)
        Wniosek.objects.create(**BASE_DATA, from_main=self.main, status=Status.done)
        update_parent(self.main)
        self.main.refresh_from_db()
        self.assertEqual(self.main.status, RequestStatus.closed)

    def test_only_oferta_done_stays_active(self):
        # Только один тип → не closed, нет активных → active
        Oferta.objects.create(**BASE_DATA, from_main=self.main, status=Status.done)
        update_parent(self.main)
        self.main.refresh_from_db()
        self.assertEqual(self.main.status, RequestStatus.active)

    def test_mixed_statuses_with_in_progress_sets_open(self):
        Oferta.objects.create(**BASE_DATA, from_main=self.main, status=Status.done)
        Zlecenie.objects.create(**BASE_DATA, from_main=self.main, status=Status.in_progress)
        Wniosek.objects.create(**BASE_DATA, from_main=self.main, status=Status.waiting)
        update_parent(self.main)
        self.main.refresh_from_db()
        self.assertEqual(self.main.status, RequestStatus.open)

    def test_cancelled_parent_is_not_touched(self):
        # Уже отменённую заявку update_parent не трогает.
        self.main.status = RequestStatus.cancelled
        self.main.save()
        Oferta.objects.create(**BASE_DATA, from_main=self.main, status=Status.done)
        update_parent(self.main)
        self.main.refresh_from_db()
        self.assertEqual(self.main.status, RequestStatus.cancelled)

    def test_deleted_parent_is_not_touched(self):
        self.main.status = RequestStatus.deleted
        self.main.save()
        update_parent(self.main)
        self.main.refresh_from_db()
        self.assertEqual(self.main.status, RequestStatus.deleted)


# ────────────────────────── handle_child_change ───────────────────────────────

class HandleChildChangeTests(TestCase):
    """Атомарная операция: меняет статус ребёнка И обновляет родителя.

    Выполняется в transaction.atomic() — если смена статуса упала,
    родитель НЕ должен измениться.
    """

    def setUp(self):
        self.main = RequestMain.objects.create(**BASE_DATA)
        self.oferta = Oferta.objects.create(**BASE_DATA, from_main=self.main)

    def test_valid_transition_updates_both_child_and_parent(self):
        handle_child_change(self.oferta, Status.in_progress, reason=None, user=None)
        self.oferta.refresh_from_db()
        self.main.refresh_from_db()
        self.assertEqual(self.oferta.status, Status.in_progress)
        # После in_progress ребёнка, родитель должен стать open
        self.assertEqual(self.main.status, RequestStatus.open)

    def test_invalid_transition_does_not_touch_parent(self):
        # Если смена статуса ребёнка падает — транзакция откатывается.
        # Статус родителя остаётся прежним.
        original_main_status = self.main.status
        with self.assertRaises(ValueError):
            handle_child_change(self.oferta, Status.waiting, reason=None, user=None)
        self.main.refresh_from_db()
        self.assertEqual(self.main.status, original_main_status)


# ────────────────────────── save_child_with_status ────────────────────────────

class SaveChildWithStatusTests(TestCase):
    """Обёртка для admin.save_model: берёт status из формы и вызывает handle_child_change.

    Возвращает True при успехе, False + messages.error при недопустимом переходе.
    MagicMock заменяет реальные request и messages_module — мы проверяем
    только возвращаемое значение и вызов messages.error.
    """

    def setUp(self):
        main = RequestMain.objects.create(**BASE_DATA)
        self.oferta = Oferta.objects.create(**BASE_DATA, from_main=main)

    def _make_form(self, status):
        # MagicMock создаёт объект с любыми атрибутами «на лету».
        # cleaned_data имитирует результат form.is_valid().
        form = MagicMock()
        form.cleaned_data = {"status": status}
        return form

    def test_valid_transition_returns_true_and_no_error(self):
        fake_messages = MagicMock()
        result = save_child_with_status(
            request=MagicMock(),
            obj=self.oferta,
            form=self._make_form(Status.in_progress),
            change=False,
            messages_module=fake_messages,
        )
        self.assertTrue(result)
        fake_messages.error.assert_not_called()

    def test_invalid_transition_returns_false_and_calls_error(self):
        # new → waiting недопустим; функция должна сообщить об ошибке через messages
        fake_messages = MagicMock()
        result = save_child_with_status(
            request=MagicMock(),
            obj=self.oferta,
            form=self._make_form(Status.waiting),
            change=False,
            messages_module=fake_messages,
        )
        self.assertFalse(result)
        # messages.error должен быть вызван ровно один раз
        fake_messages.error.assert_called_once()

    def test_change_true_reloads_status_from_db(self):
        # Когда change=True (редактирование существующего объекта), функция
        # перечитывает текущий статус из БД перед попыткой перехода.
        # Это защита от прямого присвоения obj.status через форму (обход FSM).
        self.oferta.status = Status.waiting  # прямое присвоение, не сохраняем в БД
        fake_messages = MagicMock()
        result = save_child_with_status(
            request=MagicMock(),
            obj=self.oferta,
            form=self._make_form(Status.in_progress),
            change=True,  # ← функция перечитает статус из БД (там Status.new)
            messages_module=fake_messages,
        )
        self.assertTrue(result)


# ────────────────────────── cancel_request ────────────────────────────────────

class CancelRequestTests(TestCase):
    """Отмена заявки: статус → cancelled, создаётся запись в StatusHistory."""

    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="x")
        self.main = RequestMain.objects.create(**BASE_DATA)

    def test_cancel_sets_cancelled_status(self):
        cancel_request(self.main, self.user, reason="client withdrew")
        self.main.refresh_from_db()
        self.assertEqual(self.main.status, RequestStatus.cancelled)

    def test_cancel_creates_status_history_entry(self):
        # StatusHistory хранит аудит-лог: кто, когда, почему изменил статус.
        cancel_request(self.main, self.user, reason="client withdrew")
        entry = StatusHistory.objects.get(request=self.main)
        self.assertEqual(entry.new_status, RequestStatus.cancelled)
        self.assertEqual(entry.reason, "client withdrew")
        self.assertEqual(entry.changed_by, self.user)

    def test_cancel_already_cancelled_raises(self):
        self.main.status = RequestStatus.cancelled
        self.main.save()
        with self.assertRaises(ValueError):
            cancel_request(self.main, self.user, reason="again")


# ────────────────────────── delete_request ────────────────────────────────────

class DeleteRequestTests(TestCase):
    """Удаление заявки: статус → deleted + мягкое удаление (safedelete).

    Запись остаётся в БД (доступна через all_with_deleted()), но скрыта
    из стандартного менеджера .objects.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="x")
        self.main = RequestMain.objects.create(**BASE_DATA)

    def test_delete_sets_deleted_status(self):
        delete_request(self.main, self.user, reason="cleanup")
        self.main.refresh_from_db()
        self.assertEqual(self.main.status, RequestStatus.deleted)

    def test_delete_soft_deletes_hides_from_default_manager(self):
        delete_request(self.main, self.user, reason="cleanup")
        # Стандартный менеджер не видит мягко-удалённые записи
        self.assertFalse(RequestMain.objects.filter(pk=self.main.pk).exists())
        # Но в БД запись жива — all_with_deleted() из safedelete её находит
        self.assertTrue(
            RequestMain.objects.all_with_deleted().filter(pk=self.main.pk).exists()
        )

    def test_delete_creates_status_history_entry(self):
        delete_request(self.main, self.user, reason="cleanup")
        entry = StatusHistory.objects.get(request=self.main)
        self.assertEqual(entry.new_status, RequestStatus.deleted)
        self.assertEqual(entry.reason, "cleanup")

    def test_delete_already_deleted_raises(self):
        self.main.status = RequestStatus.deleted
        self.main.save()
        with self.assertRaises(ValueError):
            delete_request(self.main, self.user, reason="again")
