from unittest.mock import MagicMock

from django.test import TestCase

from crm.zetom.models import Oferta, RequestMain, Wniosek, Zlecenie
from crm.zetom.services.services import (change_status, handle_child_change,
                                         save_child_with_status, update_parent)
from crm.zetom.services.statuses import Status

BASE_DATA = {
    "phone": "+48501600300",
    "company_name": "Zetom Sp. z o.o.",
    "email": "contact@zetom.pl",
    "company_nip": "7322215365",
}


class ChangeStatusTests(TestCase):
    def setUp(self):
        self.main = RequestMain.objects.create(**BASE_DATA)
        self.oferta = Oferta.objects.create(**BASE_DATA, from_main=self.main)

    def test_new_to_in_progress_allowed(self):
        change_status(self.oferta, Status.in_progress)
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.status, Status.in_progress)

    def test_in_progress_to_waiting_allowed(self):
        self.oferta.status = Status.in_progress
        self.oferta.save()
        change_status(self.oferta, Status.waiting)
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.status, Status.waiting)

    def test_waiting_to_done_allowed(self):
        self.oferta.status = Status.waiting
        self.oferta.save()
        change_status(self.oferta, Status.done)
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.status, Status.done)

    def test_done_back_to_waiting_or_in_progress_allowed(self):
        self.oferta.status = Status.done
        self.oferta.save()
        change_status(self.oferta, Status.in_progress)
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.status, Status.in_progress)

    def test_illegal_transition_raises(self):
        # new → waiting is not allowed
        with self.assertRaises(ValueError):
            change_status(self.oferta, Status.waiting)

    def test_same_status_is_noop(self):
        change_status(self.oferta, Status.new)
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.status, Status.new)

    def test_none_status_is_noop(self):
        change_status(self.oferta, None)
        self.oferta.refresh_from_db()
        self.assertEqual(self.oferta.status, Status.new)


class UpdateParentTests(TestCase):
    def setUp(self):
        self.main = RequestMain.objects.create(**BASE_DATA)

    def test_archived_when_no_children(self):
        update_parent(self.main)
        self.main.refresh_from_db()
        self.assertTrue(self.main.is_archived)

    def test_in_progress_takes_priority(self):
        Oferta.objects.create(**BASE_DATA, from_main=self.main, status=Status.done)
        Zlecenie.objects.create(
            **BASE_DATA, from_main=self.main, status=Status.in_progress
        )
        Wniosek.objects.create(**BASE_DATA, from_main=self.main, status=Status.waiting)

        update_parent(self.main)
        self.main.refresh_from_db()
        self.assertEqual(self.main.status, Status.in_progress)
        self.assertFalse(self.main.is_archived)

    def test_waiting_beats_new(self):
        Oferta.objects.create(**BASE_DATA, from_main=self.main, status=Status.new)
        Zlecenie.objects.create(**BASE_DATA, from_main=self.main, status=Status.waiting)
        update_parent(self.main)
        self.main.refresh_from_db()
        self.assertEqual(self.main.status, Status.waiting)

    def test_all_done_archives_parent(self):
        Oferta.objects.create(**BASE_DATA, from_main=self.main, status=Status.done)
        Zlecenie.objects.create(**BASE_DATA, from_main=self.main, status=Status.done)
        update_parent(self.main)
        self.main.refresh_from_db()
        self.assertEqual(self.main.status, Status.done)
        self.assertTrue(self.main.is_archived)

    def test_any_non_done_keeps_parent_active(self):
        Oferta.objects.create(**BASE_DATA, from_main=self.main, status=Status.done)
        Zlecenie.objects.create(**BASE_DATA, from_main=self.main, status=Status.new)
        update_parent(self.main)
        self.main.refresh_from_db()
        self.assertFalse(self.main.is_archived)


class HandleChildChangeTests(TestCase):
    def setUp(self):
        self.main = RequestMain.objects.create(**BASE_DATA)
        self.oferta = Oferta.objects.create(**BASE_DATA, from_main=self.main)

    def test_changes_status_and_updates_parent(self):
        handle_child_change(self.oferta, Status.in_progress)
        self.oferta.refresh_from_db()
        self.main.refresh_from_db()
        self.assertEqual(self.oferta.status, Status.in_progress)
        self.assertEqual(self.main.status, Status.in_progress)
        self.assertFalse(self.main.is_archived)

    def test_invalid_transition_does_not_touch_parent(self):
        original_main_status = self.main.status
        with self.assertRaises(ValueError):
            handle_child_change(self.oferta, Status.waiting)  # new → waiting invalid
        self.main.refresh_from_db()
        self.assertEqual(self.main.status, original_main_status)


class SaveChildWithStatusTests(TestCase):
    def setUp(self):
        self.main = RequestMain.objects.create(**BASE_DATA)
        self.oferta = Oferta.objects.create(**BASE_DATA, from_main=self.main)

    def _make_form(self, status):
        form = MagicMock()
        form.cleaned_data = {"status": status}
        return form

    def test_returns_true_on_valid_transition(self):
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

    def test_returns_false_and_reports_error_on_invalid_transition(self):
        fake_messages = MagicMock()
        result = save_child_with_status(
            request=MagicMock(),
            obj=self.oferta,
            form=self._make_form(Status.waiting),  # new → waiting invalid
            change=False,
            messages_module=fake_messages,
        )
        self.assertFalse(result)
        fake_messages.error.assert_called_once()
