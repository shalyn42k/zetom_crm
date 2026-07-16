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
from crm.status_manager.services.statuses import RequestStatus
from crm.zetom.models import RequestMain
from crm.zetom.services.status_orchestration import ReasonRequired, apply_status_change

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
