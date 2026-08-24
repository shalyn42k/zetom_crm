# ──────────────────────────────────────────────────────────────────────────────
# ТЕСТЫ document chain (Task 10 + Task 11)
#
# Task 10 — мягкая цепочка Oferta -> Zlecenie -> Wniosek:
#   • Zlecenie.from_oferta / Wniosek.from_zlecenie — nullable FK, SET_NULL.
#   • Удаление родителя не убивает дочерний документ — просто обнуляет ссылку.
#   • from_main никогда не трогается цепочкой (это отдельная связь).
#
# Task 10 tests: DocumentChainModelTests.
# ──────────────────────────────────────────────────────────────────────────────

from django.test import TestCase
from safedelete.config import HARD_DELETE

from crm.zetom.models import Oferta, RequestMain, Wniosek, Zlecenie

BASE_DATA = {
    "phone": "+48501600300",
    "email": "contact@zetom.pl",
}


# ─────────────────────────── Task 10: модельная цепочка ───────────────────────

class DocumentChainModelTests(TestCase):
    """Zlecenie.from_oferta / Wniosek.from_zlecenie — мягкая цепочка."""

    def setUp(self):
        self.main = RequestMain.objects.create(**BASE_DATA)
        self.oferta = Oferta.objects.create(**BASE_DATA, from_main=self.main)
        self.zlecenie = Zlecenie.objects.create(**BASE_DATA, from_main=self.main)

    # ---- Zlecenie.from_oferta ----

    def test_zlecenie_can_be_created_without_oferta(self):
        z = Zlecenie.objects.create(**BASE_DATA, from_main=self.main, from_oferta=None)
        self.assertIsNone(z.from_oferta)

    def test_zlecenie_links_back_to_oferta(self):
        z = Zlecenie.objects.create(**BASE_DATA, from_main=self.main, from_oferta=self.oferta)
        self.assertIn(z, self.oferta.zlecenia.all())

    def test_deleting_oferta_keeps_zlecenie(self):
        z = Zlecenie.objects.create(**BASE_DATA, from_main=self.main, from_oferta=self.oferta)
        self.oferta.delete(force_policy=HARD_DELETE)
        z.refresh_from_db()
        self.assertIsNone(z.from_oferta)
        self.assertEqual(z.from_main, self.main)

    # ---- Wniosek.from_zlecenie ----

    def test_wniosek_can_be_created_without_zlecenie(self):
        w = Wniosek.objects.create(**BASE_DATA, from_main=self.main, from_zlecenie=None)
        self.assertIsNone(w.from_zlecenie)

    def test_wniosek_links_back_to_zlecenie(self):
        w = Wniosek.objects.create(**BASE_DATA, from_main=self.main, from_zlecenie=self.zlecenie)
        self.assertIn(w, self.zlecenie.wnioski.all())

    def test_deleting_zlecenie_keeps_wniosek(self):
        w = Wniosek.objects.create(**BASE_DATA, from_main=self.main, from_zlecenie=self.zlecenie)
        self.zlecenie.delete(force_policy=HARD_DELETE)
        w.refresh_from_db()
        self.assertIsNone(w.from_zlecenie)
        self.assertEqual(w.from_main, self.main)
