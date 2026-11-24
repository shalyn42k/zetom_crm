# claude
# ──────────────────────────────────────────────────────────────────────────────
# ТЕСТЫ request_duplicate_finder
#
# find_request_duplicates(src) ищет похожие заявки (RequestNull + активные
# RequestMain) по тем же сигналам, что и Client-матчер: phone/email/NIP/
# company/name/domain. Сам src всегда исключается, cancelled/deleted Main —
# тоже.
# ──────────────────────────────────────────────────────────────────────────────

from django.test import TestCase

from crm.status_manager.services.statuses import RequestStatus
from crm.zetom.models import RequestMain, RequestNull
from crm.zetom.services.request_duplicate_finder import (
    KIND_MAIN, KIND_NULL, find_request_duplicates,
)

BASE = {
    "first_name": "Jan",
    "last_name": "Kowalski",
    "phone": "+48501600300",
    "email": "jan@zetom.pl",
    "company_name": "Zetom",
}


class FindRequestDuplicatesTests(TestCase):
    def test_exact_phone_is_strong(self):
        src = RequestNull.objects.create(**BASE)
        RequestMain.objects.create(**BASE)
        results = find_request_duplicates(src)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].is_strong)
        self.assertEqual(results[0].kind, KIND_MAIN)

    def test_source_itself_is_excluded(self):
        src = RequestNull.objects.create(**BASE)
        results = find_request_duplicates(src)
        self.assertEqual(results, [])

    def test_finds_both_null_and_main(self):
        src = RequestNull.objects.create(**BASE)
        RequestNull.objects.create(**BASE)
        RequestMain.objects.create(**BASE)
        results = find_request_duplicates(src)
        kinds = {c.kind for c in results}
        self.assertEqual(kinds, {KIND_NULL, KIND_MAIN})
        self.assertEqual(len(results), 2)

    def test_cancelled_and_deleted_main_skipped(self):
        src = RequestNull.objects.create(**BASE)
        RequestMain.objects.create(**BASE, status=RequestStatus.cancelled)
        RequestMain.objects.create(**BASE, status=RequestStatus.deleted)
        self.assertEqual(find_request_duplicates(src), [])

    def test_no_signal_returns_empty(self):
        src = RequestNull.objects.create(**BASE)
        RequestMain.objects.create(
            first_name="Anna", last_name="Nowak",
            phone="+48999888777", email="anna@other.com",
            company_name="OtherCo",
        )
        self.assertEqual(find_request_duplicates(src), [])

    def test_sorted_score_descending(self):
        src = RequestNull.objects.create(**BASE)
        # weak: only same email domain
        RequestMain.objects.create(
            first_name="X", last_name="Y",
            phone="+48111222333", email="someoneelse@zetom.pl",
            company_name="DiffCo",
        )
        # strong: exact phone + email
        RequestMain.objects.create(**BASE)
        results = find_request_duplicates(src)
        self.assertEqual(len(results), 2)
        self.assertGreaterEqual(results[0].score, results[1].score)
        self.assertTrue(results[0].is_strong)

    def test_works_with_requestmain_source(self):
        src = RequestMain.objects.create(**BASE)
        RequestMain.objects.create(**BASE)
        results = find_request_duplicates(src)
        # other main matches, src excluded
        self.assertEqual(len(results), 1)
        self.assertNotEqual(results[0].obj.pk, src.pk)
