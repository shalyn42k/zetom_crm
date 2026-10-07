# ──────────────────────────────────────────────────────────────────────────────
# ТЕСТЫ STATUS MANAGER
#
# Что тут тестируется:
#   • StatusHistory — модель аудит-лога смены статусов RequestMain
#   • apply_status_change — оркестратор смены статуса из change-view RequestMain
#
# apply_status_change — точка входа из admin change-view:
#   1. Единственный статус, который можно установить вручную — cancelled
#   2. Требует reason (бросает ReasonRequired, если его нет)
#   3. Делегирует в cancel_request
#   4. Любой другой статус (active/open/closed/inactive/deleted) отклоняется:
#      они либо автоматические (update_parent), либо идут через отдельный
#      delete-flow (RequestMainAdmin.delete_view), а не через эту функцию
# ──────────────────────────────────────────────────────────────────────────────

from django.contrib.auth import get_user_model
from django.test import TestCase

from crm.status_manager.models import StatusHistory
from crm.status_manager.services.status_service import update_parent
from crm.status_manager.services.statuses import RequestStatus, Status
from crm.zetom.models import RequestMain
from crm.zetom.services.request_service import approve_oferta_action
from crm.zetom.services.status_orchestration import (
    ReasonRequired, apply_status_change, mark_child_done,
)

User = get_user_model()

BASE_DATA = {
    "phone": "+48501600300",
    "email": "contact@zetom.pl",
}


# ─────────────────────────── StatusHistory model ──────────────────────────────

class StatusHistoryModelTests(TestCase):
    """Аудит-лог смены статусов. Создаётся автоматически через сервисы."""

    def test_str_contains_request_and_new_status(self):
        user = User.objects.create_user(username="tester", password="x")
        main = RequestMain.objects.create(**BASE_DATA, company_name="Zetom")
        entry = StatusHistory.objects.create(
            request=main,
            old_status=RequestStatus.active,
            new_status=RequestStatus.open,
            reason="",
            changed_by=user,
        )
        # __str__ должен содержать название компании (через request.__str__) и новый статус
        self.assertIn("Zetom", str(entry))
        self.assertIn(RequestStatus.open, str(entry))

    def test_default_ordering_is_newest_first(self):
        # Meta.ordering = ["-changed_at"] — новые записи первыми
        user = User.objects.create_user(username="tester", password="x")
        main = RequestMain.objects.create(**BASE_DATA)
        StatusHistory.objects.create(
            request=main, old_status=RequestStatus.active,
            new_status=RequestStatus.open, reason="", changed_by=user,
        )
        StatusHistory.objects.create(
            request=main, old_status=RequestStatus.open,
            new_status=RequestStatus.closed, reason="", changed_by=user,
        )
        entries = list(StatusHistory.objects.all())
        # Первая запись в queryset — последняя созданная (closed)
        self.assertEqual(entries[0].new_status, RequestStatus.closed)


# ─────────────────────────── apply_status_change ──────────────────────────────

class ApplyStatusChangeTests(TestCase):
    """Оркестратор смены статуса RequestMain из admin change-view.

    Единственный статус, который сотрудник/админ может установить руками —
    cancelled (с обязательной причиной). Всё остальное — либо automatика
    (update_parent), либо отдельный delete-flow (RequestMainAdmin.delete_view),
    и через apply_status_change недостижимо.

    ReasonRequired — кастомное исключение-сигнал:
        «Нужна причина → покажи форму ввода reason».
        Это НЕ ошибка, это flow-control.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="manager", password="x")
        self.main = RequestMain.objects.create(**BASE_DATA)

    def test_automatic_status_cannot_be_set_manually(self):
        with self.assertRaises(ValueError):
            apply_status_change(self.main, self.user, RequestStatus.open)

    def test_deleted_cannot_be_set_through_this_path(self):
        # Deleted идёт только через RequestMainAdmin.delete_view, не отсюда.
        with self.assertRaises(ValueError):
            apply_status_change(self.main, self.user, RequestStatus.deleted, reason="spam")

    def test_inactive_cannot_be_set_manually(self):
        with self.assertRaises(ValueError):
            apply_status_change(self.main, self.user, RequestStatus.inactive, reason="on hold")

    def test_invalid_status_string_raises_value_error(self):
        with self.assertRaises(ValueError):
            apply_status_change(self.main, self.user, "nonsense_status")

    def test_cancelled_without_reason_raises_reason_required(self):
        with self.assertRaises(ReasonRequired):
            apply_status_change(self.main, self.user, RequestStatus.cancelled)

    def test_cancelled_with_reason_changes_status_and_creates_history(self):
        apply_status_change(self.main, self.user, RequestStatus.cancelled, reason="client withdrew")
        self.main.refresh_from_db()
        self.assertEqual(self.main.status, RequestStatus.cancelled)
        entry = StatusHistory.objects.get(request=self.main)
        self.assertEqual(entry.old_status, RequestStatus.active)
        self.assertEqual(entry.new_status, RequestStatus.cancelled)
        self.assertEqual(entry.reason, "client withdrew")
        self.assertEqual(entry.changed_by, self.user)

    def test_cancelled_twice_raises_value_error(self):
        apply_status_change(self.main, self.user, RequestStatus.cancelled, reason="client withdrew")
        with self.assertRaises(ValueError):
            apply_status_change(self.main, self.user, RequestStatus.cancelled, reason="again")


# ─────────────────────────── update_parent / StatusHistory ────────────────────

class UpdateParentStatusHistoryTests(TestCase):
    """update_parent() drives every active<->open<->closed transition, but
    used to never log to StatusHistory — only the manual Cancel action did.
    The RequestMain 'Historia' panel renders status_history, so it showed
    nothing for the vast majority of real status changes."""

    def test_creating_first_child_logs_active_to_open_or_stays_logged_once(self):
        main = RequestMain.objects.create(**BASE_DATA)
        self.assertEqual(StatusHistory.objects.filter(request=main).count(), 0)

        oferta = approve_oferta_action(main.pk)  # status=new -> parent stays active
        main.refresh_from_db()
        self.assertEqual(main.status, RequestStatus.active)
        # no transition happened (active -> active) -> no history row
        self.assertEqual(StatusHistory.objects.filter(request=main).count(), 0)

        mark_child_done(oferta, user=None)  # done oferta, no zlecenie/wniosek yet
        self.assertEqual(StatusHistory.objects.filter(request=main).count(), 0)

    def test_logs_transition_to_open_when_a_child_becomes_active(self):
        main = RequestMain.objects.create(**BASE_DATA)
        oferta = approve_oferta_action(main.pk)
        oferta.status = Status.in_progress
        oferta.save()

        update_parent(main)

        main.refresh_from_db()
        self.assertEqual(main.status, RequestStatus.open)
        entry = StatusHistory.objects.get(request=main)
        self.assertEqual(entry.old_status, RequestStatus.active)
        self.assertEqual(entry.new_status, RequestStatus.open)
        self.assertIsNone(entry.changed_by)

    def test_does_not_log_when_status_is_unchanged(self):
        main = RequestMain.objects.create(**BASE_DATA)
        update_parent(main)  # no children -> stays active -> active
        self.assertEqual(StatusHistory.objects.filter(request=main).count(), 0)

    def test_does_not_log_for_a_cancelled_request(self):
        user = User.objects.create_user(username="manager2", password="x")
        main = RequestMain.objects.create(**BASE_DATA)
        apply_status_change(main, user, RequestStatus.cancelled, reason="x")
        StatusHistory.objects.filter(request=main).delete()  # isolate update_parent

        update_parent(main)

        self.assertEqual(StatusHistory.objects.filter(request=main).count(), 0)
