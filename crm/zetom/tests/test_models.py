# ──────────────────────────────────────────────────────────────────────────────
# ТЕСТЫ МОДЕЛЕЙ
#
# Что тут тестируется и зачем:
#   • Поля действительно сохраняются в БД (refresh_from_db перечитывает из БД,
#     не берёт значения из Python-объекта в памяти).
#   • Значения по умолчанию выставляются правильно.
#   • Валидаторы модели работают (full_clean() вызывает их явно).
#   • Связи между моделями (FK, OneToOne) ведут себя как объявлено.
#   • Мягкое удаление (safedelete) каскадирует на дочерние записи.
#
# Каждый тест проверяет ОДНУ вещь — это делает ошибки понятными.
# ──────────────────────────────────────────────────────────────────────────────

from django.core.exceptions import ValidationError
from django.test import TestCase

from crm.status_manager.services.statuses import RequestStatus, Status
from crm.zetom.models import (
    DepartmentsVariants,
    Oferta,
    RequestMain,
    RequestNull,
    Wniosek,
    Zlecenie,
)

# Минимальный набор обязательных полей RequestTemplate.
# phone и email — null=False, blank=False, остальные опциональны.
BASE_DATA = {
    "phone": "+48501600300",
    "email": "contact@zetom.pl",
}


# ─────────────────────────── RequestNull ──────────────────────────────────────

class RequestNullModelTests(TestCase):
    """RequestNull — «черновик» заявки с публичной формы.

    Поля phone/email обязательны. company_nip валидируется регулярным
    выражением ^\\d{10}$ (NIP по польскому стандарту).
    """

    def test_create_persists_required_fields(self):
        # objects.create() сохраняет запись. refresh_from_db() перечитывает её из БД —
        # это гарантирует, что проверяем данные из БД, а не из Python-объекта в памяти.
        obj = RequestNull.objects.create(
            **BASE_DATA,
            first_name="Jan",
            last_name="Kowalski",
            company_name="Zetom Sp. z o.o.",
        )
        obj.refresh_from_db()
        self.assertEqual(obj.email, "contact@zetom.pl")
        self.assertEqual(obj.company_name, "Zetom Sp. z o.o.")
        self.assertEqual(obj.first_name, "Jan")

    def test_departments_default_is_empty_list(self):
        # departments — ArrayField с default=list. Важно проверить, что это [],
        # а не None (null=False на поле).
        obj = RequestNull.objects.create(**BASE_DATA)
        obj.refresh_from_db()
        self.assertEqual(obj.departments, [])

    def test_str_returns_company_name(self):
        obj = RequestNull.objects.create(**BASE_DATA, company_name="Zetom")
        self.assertEqual(str(obj), "Zetom")

    def test_full_name_property_combines_first_and_last(self):
        # full_name — property из RequestTemplate: склеивает first_name + last_name.
        obj = RequestNull.objects.create(**BASE_DATA, first_name="Jan", last_name="Kowalski")
        self.assertEqual(obj.full_name, "Jan Kowalski")

    def test_full_name_with_only_first_name(self):
        # filter(None, ...) отсеивает пустые строки — не получим «Jan »
        obj = RequestNull.objects.create(**BASE_DATA, first_name="Jan")
        self.assertEqual(obj.full_name, "Jan")

    def test_full_name_empty_when_no_names(self):
        obj = RequestNull.objects.create(**BASE_DATA)
        self.assertEqual(obj.full_name, "")

    def test_nip_validator_rejects_non_digits(self):
        # full_clean() запускает validators на уровне модели.
        # RegexValidator бросает ValidationError если NIP содержит не-цифры.
        obj = RequestNull(**BASE_DATA, company_nip="ABC1234567")
        with self.assertRaises(ValidationError):
            obj.full_clean()

    def test_nip_validator_rejects_wrong_length(self):
        # NIP обязан быть ровно 10 символов.
        obj = RequestNull(**BASE_DATA, company_nip="12345")
        with self.assertRaises(ValidationError):
            obj.full_clean()

    def test_nip_validator_accepts_valid_10_digit_nip(self):
        # Десять цифр — корректный NIP. full_clean() не бросает исключение.
        obj = RequestNull(**BASE_DATA, company_nip="7322215365")
        obj.full_clean()  # не падает — тест проходит


# ─────────────────────────── RequestMain ──────────────────────────────────────

class RequestMainModelTests(TestCase):
    """RequestMain — основная рабочая заявка.

    Отличается от RequestNull: имеет status (из RequestStatus), from_null,
    address. Статус по умолчанию — active (не Status.new — это для дочерних!).
    """

    def test_default_status_is_active(self):
        # RequestMain использует RequestStatus (active/open/closed/...),
        # а НЕ детский Status (new/in_progress/waiting/done).
        main = RequestMain.objects.create(**BASE_DATA)
        self.assertEqual(main.status, RequestStatus.active)

    def test_from_null_link_is_stored(self):
        null = RequestNull.objects.create(**BASE_DATA)
        main = RequestMain.objects.create(**BASE_DATA, from_null=null)
        main.refresh_from_db()
        self.assertEqual(main.from_null, null)

    def test_from_null_becomes_none_when_null_hard_deleted(self):
        # on_delete=SET_NULL: если RequestNull физически удалён,
        # from_null обнуляется на связанном RequestMain.
        # force_policy=0 — HARD_DELETE из safedelete (обходит мягкое удаление).
        null = RequestNull.objects.create(**BASE_DATA)
        main = RequestMain.objects.create(**BASE_DATA, from_null=null)
        null.delete(force_policy=0)
        main.refresh_from_db()
        self.assertIsNone(main.from_null)


# ─────────────────────────── Дочерние модели ──────────────────────────────────

class ChildModelsTests(TestCase):
    """Oferta / Zlecenie / Wniosek — дочерние документы к RequestMain.

    Создаются через approve_*_action из request_service (в реальности).
    Здесь тестируем только связи и поведение safedelete каскада.
    """

    def setUp(self):
        # setUp() вызывается перед КАЖДЫМ методом test_*:
        # каждый тест получает свежий main без остатков от других тестов.
        self.main = RequestMain.objects.create(**BASE_DATA)

    def test_oferta_default_status_is_new(self):
        oferta = Oferta.objects.create(**BASE_DATA, from_main=self.main)
        self.assertEqual(oferta.status, Status.new)

    def test_oferta_visible_via_reverse_relation(self):
        oferta = Oferta.objects.create(**BASE_DATA, from_main=self.main)
        # Django создаёт обратный менеджер oferta_set через ForeignKey
        self.assertIn(oferta, self.main.oferta_set.all())

    def test_zlecenie_linked_to_main(self):
        zlec = Zlecenie.objects.create(**BASE_DATA, from_main=self.main)
        self.assertEqual(zlec.from_main, self.main)
        self.assertIn(zlec, self.main.zlecenie_set.all())

    def test_wniosek_linked_to_main(self):
        wn = Wniosek.objects.create(**BASE_DATA, from_main=self.main)
        self.assertEqual(wn.from_main, self.main)
        self.assertIn(wn, self.main.wniosek_set.all())

    def test_soft_delete_cascade_hides_children_from_default_manager(self):
        # safedelete с SOFT_DELETE_CASCADE: мягкое удаление main помечает
        # дочерние записи как удалённые, но НЕ убирает их из БД.
        #
        # После self.main.delete():
        #   .objects — стандартный менеджер, скрывает мягко-удалённые → 0
        #   .objects.all_with_deleted() — видит всё → 1
        Oferta.objects.create(**BASE_DATA, from_main=self.main)
        Zlecenie.objects.create(**BASE_DATA, from_main=self.main)
        Wniosek.objects.create(**BASE_DATA, from_main=self.main)

        self.main.delete()  # мягкое удаление

        self.assertEqual(Oferta.objects.count(), 0)
        self.assertEqual(Zlecenie.objects.count(), 0)
        self.assertEqual(Wniosek.objects.count(), 0)
        # Физически в БД объекты живы — all_with_deleted() из safedelete
        self.assertEqual(Oferta.objects.all_with_deleted().count(), 1)
        self.assertEqual(Zlecenie.objects.all_with_deleted().count(), 1)
        self.assertEqual(Wniosek.objects.all_with_deleted().count(), 1)

    def test_hard_delete_cascades_and_removes_children_from_db(self):
        # force_policy=0 → HARD_DELETE: физически удаляет main из БД.
        # БД-уровневый CASCADE удаляет дочерние записи.
        Oferta.objects.create(**BASE_DATA, from_main=self.main)
        self.main.delete(force_policy=0)
        self.assertEqual(Oferta.objects.all_with_deleted().count(), 0)
