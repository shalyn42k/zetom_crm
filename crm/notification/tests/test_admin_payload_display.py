# ──────────────────────────────────────────────────────────────────────────────
# ТЕСТЫ _pretty_json (crm/notification/admin.py) — raw payload dump
# (the "Dane" section on a Notification/EmailNotification's change page).
#
# Found on /notification/notification/<id>/change/: every row there showed
# the raw Python payload key ("actor_name", "new_status", ...) and, for
# status-like fields, the raw stored code ("active", "cancelled") — plain
# Python code building the HTML (format_html_join), never passing through
# gettext. _PAYLOAD_KEY_LABELS / _payload_display_value translate the key
# and known status-like values at render time.
# ──────────────────────────────────────────────────────────────────────────────

from django.test import TestCase
from django.utils import translation

from crm.notification.admin import _pretty_json
from crm.status_manager.services.statuses import RequestStatus
from crm.zetom.models import RequestSource


class PrettyJsonLabelTranslationTests(TestCase):
    def test_keys_translated_in_polish(self):
        payload = {"actor_name": "system", "old_status": "active", "new_status": "cancelled"}
        with translation.override("pl"):
            rendered = str(_pretty_json(payload))
        self.assertIn("Wykonawca", rendered)
        self.assertIn("Poprzedni status", rendered)
        self.assertIn("Nowy status", rendered)
        self.assertNotIn("actor_name", rendered)
        self.assertNotIn("old_status<", rendered)

    def test_status_values_translated_in_polish(self):
        payload = {
            "old_status": RequestStatus.active,
            "new_status": RequestStatus.cancelled,
        }
        with translation.override("pl"):
            rendered = str(_pretty_json(payload))
        self.assertIn("Aktywne", rendered)
        self.assertIn("Anulowane", rendered)
        self.assertNotIn(">active<", rendered)
        self.assertNotIn(">cancelled<", rendered)

    def test_decision_value_translated_in_polish(self):
        with translation.override("pl"):
            rendered = str(_pretty_json({"decision": "approved"}))
        self.assertIn("Zatwierdzone", rendered)
        self.assertNotIn(">approved<", rendered)

    def test_source_value_translated_in_polish(self):
        with translation.override("pl"):
            rendered = str(_pretty_json({"source": RequestSource.PHONE}))
        self.assertIn("Telefon", rendered)

    def test_unknown_key_falls_back_to_raw_name(self):
        with translation.override("pl"):
            rendered = str(_pretty_json({"some_future_key": "x"}))
        self.assertIn("some_future_key", rendered)

    def test_none_value_renders_as_dash(self):
        with translation.override("pl"):
            rendered = str(_pretty_json({"actor_name": None}))
        self.assertIn("—", rendered)

    def test_renders_in_english_by_default(self):
        payload = {"old_status": "active", "new_status": "cancelled"}
        rendered = str(_pretty_json(payload))
        self.assertIn("Old status", rendered)
        self.assertIn("Active", rendered)
        self.assertIn("Cancelled", rendered)
