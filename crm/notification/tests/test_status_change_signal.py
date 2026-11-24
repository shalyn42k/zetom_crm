# ──────────────────────────────────────────────────────────────────────────────
# ТЕСТЫ _notify_inapp_on_request_status_change (crm/notification/signals.py)
# и request_status_label (crm/status_manager/templatetags/status_labels.py)
#
# Баг: notification/inapp/staff/request_status_changed.txt quoted the raw
# RequestStatus code ("active"/"cancelled") instead of its translated
# label, so a Polish-locale user reading "system zmienił status z ... na
# ..." saw raw English codes inside an otherwise Polish sentence.
#
# Fix is deliberately render-time, not write-time: payload keeps storing
# the raw old_status/new_status codes (as before — also what the admin's
# raw-payload debug dump shows), and the template resolves them to a
# translated label via the request_status_label filter when rendered. A
# first attempt baked old_status_label/new_status_label into the payload
# at write time instead — that broke for the very case this bug is about:
# the active language when a signal fires isn't necessarily the viewer's,
# so the label would've been frozen in whatever language was active when
# the status actually changed, not the one the recipient is reading in.
# ──────────────────────────────────────────────────────────────────────────────

from django.contrib.auth import get_user_model
from django.template import Context, Template
from django.test import TestCase
from django.utils import translation

from crm.notification.models import Notification, NotificationKind
from crm.notification.utils import render_notification
from crm.status_manager.services.statuses import RequestStatus
from crm.zetom.models import RequestMain

User = get_user_model()

BASE = {"phone": "+48501600300", "email": "jan@zetom.pl"}


class StatusChangeNotificationPayloadTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # falls back to admins when no owners/dep_heads are assigned
        cls.admin = User.objects.create_superuser("admin_recv", "a@zetom.pl", "x")

    def _change_status(self, main, new_status):
        main.status = new_status
        main.save()
        main.refresh_from_db()

    def test_payload_keeps_raw_status_codes(self):
        main = RequestMain.objects.create(**BASE, status=RequestStatus.active)
        self._change_status(main, RequestStatus.open)

        notif = Notification.objects.get(
            recipient=self.admin, kind=NotificationKind.STATUS_CHANGE,
        )
        self.assertEqual(notif.payload["old_status"], RequestStatus.active)
        self.assertEqual(notif.payload["new_status"], RequestStatus.open)

    def test_rendered_body_quotes_translated_labels_in_polish(self):
        main = RequestMain.objects.create(**BASE, status=RequestStatus.active)
        self._change_status(main, RequestStatus.open)

        notif = Notification.objects.get(
            recipient=self.admin, kind=NotificationKind.STATUS_CHANGE,
        )
        with translation.override("pl"):
            title, body = render_notification(notif)
        self.assertNotIn('"active"', body)
        self.assertNotIn('"open"', body)
        self.assertIn("Aktywne", body)
        self.assertIn("Otwarte", body)

    def test_rendered_body_in_english_by_default(self):
        main = RequestMain.objects.create(**BASE, status=RequestStatus.active)
        self._change_status(main, RequestStatus.open)

        notif = Notification.objects.get(
            recipient=self.admin, kind=NotificationKind.STATUS_CHANGE,
        )
        title, body = render_notification(notif)
        self.assertIn("Active", body)
        self.assertIn("Open", body)

    def test_same_notification_renders_per_viewer_language_not_creation_time(self):
        # claude — the whole point of resolving at render time: one stored
        # notification, read back in two different languages, each viewer
        # sees their own.
        main = RequestMain.objects.create(**BASE, status=RequestStatus.active)
        self._change_status(main, RequestStatus.open)
        notif = Notification.objects.get(
            recipient=self.admin, kind=NotificationKind.STATUS_CHANGE,
        )

        with translation.override("en"):
            _, body_en = render_notification(notif)
        with translation.override("pl"):
            _, body_pl = render_notification(notif)

        self.assertIn("Active", body_en)
        self.assertIn("Aktywne", body_pl)
        self.assertNotIn("Aktywne", body_en)
        self.assertNotIn("Active", body_pl)


class RequestStatusLabelFilterTests(TestCase):
    TEMPLATE = "{% load status_labels %}{{ code|request_status_label }}"

    def test_known_code_resolves_to_label(self):
        t = Template(self.TEMPLATE)
        self.assertEqual(
            t.render(Context({"code": RequestStatus.cancelled})), "Cancelled",
        )

    def test_unknown_code_falls_back_to_raw_value(self):
        t = Template(self.TEMPLATE)
        self.assertEqual(
            t.render(Context({"code": "not_a_real_status"})), "not_a_real_status",
        )
