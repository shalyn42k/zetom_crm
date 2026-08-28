# claude
# ──────────────────────────────────────────────────────────────────────────────
# ТЕСТЫ ТОКЕНОВ ВИЗУАЛЬНОГО ЯЗЫКА (Task 2 — visual-tokens-unification)
#
# Что тут тестируется:
#   • static/css/tokens.css существует и объявляет все семантические роли +
#     статусные цвета + тени/радиусы из спека §4.1.
#   • templates/unfold/layouts/skeleton.html подключает tokens.css РАНЬШЕ
#     custom_admin.css (порядок важен для каскада — см. task-2-brief.md).
#   • Инвариант "hex-литералы только в tokens.css": растущий список уже
#     мигрированных файлов. На этой задаче список пуст — тест существует,
#     чтобы последующие задачи добавляли в него свои файлы по одному.
#
# SimpleTestCase — тесты читают файлы с диска, БД не нужна.
# ──────────────────────────────────────────────────────────────────────────────

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

TOKENS_CSS = settings.BASE_DIR / "static" / "css" / "tokens.css"
SKELETON_HTML = (
    settings.BASE_DIR / "templates" / "unfold" / "layouts" / "skeleton.html"
)

# Задача 2: список пуст — ни один файл ещё не мигрирован на токены.
# Каждая следующая задача добавляет сюда свой файл (по одному за задачу).
# Задача 3: static/admin/css/custom_admin.css мигрирован на роли из tokens.css.
# Задача 4: карточки clients (company_card.css, client_pages.css) мигрированы,
# заодно устранён дрейф company_card.css (--border/--purple/--shadow-lg).
# Задача 5: validation_window.css, email_form.css, notification_badge.css —
# три мелких файла. validation_window.css заодно избавлен от шедоуинга
# --green/--red/--amber/--blue/--purple/--slate/--shadow-sm/--shadow-lg и
# от левых --color-primary-500/600/700 (перекрывали шкалу Unfold). У
# email_form.css основная часть цветов уже была на oklch(...), не hex —
# только 5 литералов конвертированы 1:1 (rgb()/white), сами --zf-*
# переменные не перепривязаны к общим ролям (см. комментарий в файле).
# Задача 6: static/zetom/css/requestmain_detail.css — самый рискованный файл
# (1191 строка, 175 литералов, 40% всей краски проекта). Убран шедоуинг
# --surface/--border/--text/--green/--green-bright/--red/--amber/--blue/
# --purple/--slate/--input-bg/--shadow-lg/--r-lg внутри .rm-scrim (эти имена
# уже есть в tokens.css); --rm-st-* отображены на статусные токены
# (--rm-st-closed — на --text-subtle, у него нет статусного аналога).
MIGRATED_FILES = [
    "static/admin/css/custom_admin.css",
    "static/clients/css/company_card.css",
    "static/clients/css/client_pages.css",
    "static/zetom/css/validation_window.css",
    "crm/zetom/static/zetom/css/email_form.css",
    "static/admin/css/notification_badge.css",
    "static/zetom/css/requestmain_detail.css",
]

# Hex-литерал цвета: #fff, #ffffff, #ffffffcc и т.п. rgba(...) сюда не
# попадает — это не hex и не покрывается инвариантом (см. бриф).
HEX_COLOR_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")

# claude — fix-round (Task 5, second pass): the hex-only regex above has a
# loophole — `rgb(90, 90, 255)` is the exact same hardcoded pixels as
# `#5a5aff`, just spelled differently, and it slid straight through. This
# regex closes that: it matches any rgb()/rgba() with literal numeric
# channels, in any of the notations seen in this codebase (with or without
# spaces after commas, with or without an alpha channel).
#
# Exemptions (deliberately narrow, not "any rgba() is fine"):
#   1. Pure black — r=g=b=0, e.g. rgba(0,0,0,.6) or rgb(0, 0, 0). Treated
#      the same as the `white`/`black` CSS keywords already used freely
#      elsewhere in these files (see email_form.css, validation_window.css):
#      a universal colour, not a project palette decision, so it needs no
#      role. This is checked in code below (RGB_LITERAL_RE captures the
#      channels; the test filters out the (0, 0, 0) triple), not in the
#      regex itself, so the same pattern also matches — and therefore still
#      *reports* — non-black triples for a clear failure message.
#   2. `%23`-encoded colours inside `url("data:image/svg+xml...")` — those
#      aren't rgb()/rgba() at all (SVG uses its own `stroke='%23...'`
#      attribute encoding) and can't use var() in that position, so this
#      regex never touches them; no special-casing needed.
RGB_LITERAL_RE = re.compile(
    r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*(?:,\s*[\d.]+\s*)?\)"
)


def _non_exempt_rgb_matches(content):
    """rgb()/rgba() channel triples in `content`, minus the pure-black
    exemption (see RGB_LITERAL_RE comment above)."""
    return [m for m in RGB_LITERAL_RE.findall(content) if m != ("0", "0", "0")]


# claude — fix-round: RGB_LITERAL_RE is enforced only on the three files
# Task 5 actually owns. static/admin/css/custom_admin.css (Task 3) and
# static/clients/css/company_card.css / client_pages.css (Task 4) already
# contain pre-existing non-exempt literal rgba() tints that predate this
# stricter check (e.g. custom_admin.css's rgba(48, 214, 114, ...) green
# tints and rgba(136, 152, 170, ...) slate tints; company_card.css's
# rgba(8, 11, 15, .6) modal scrim) — the same "hardcoded pixels in a
# different notation" bug this fix-round found in email_form.css and
# validation_window.css, just not yet caught in those two files because
# they're out of Task 5's file scope ("do NOT modify any other CSS file").
# Deliberately NOT silently widening MIGRATED_FILES' hex check to also
# cover rgb() for those three — that would either fail the suite on files
# this task isn't allowed to touch, or require rewriting someone else's
# already-shipped, already-reviewed work as a side effect of a test-only
# ask. Named here as follow-up debt instead. Every file added to
# RGB_STRICT_FILES from here on (this task's three, and whatever migrates
# next) must stay clean of it going forward.
RGB_STRICT_FILES = [
    "static/zetom/css/validation_window.css",
    "crm/zetom/static/zetom/css/email_form.css",
    "static/admin/css/notification_badge.css",
]

EXPECTED_ROLES = [
    "--surface",
    "--surface-soft",
    "--border",
    "--border-strong",
    "--text",
    "--text-muted",
    "--text-subtle",
    "--input-bg",
    "--input-border",
    "--accent",
]

EXPECTED_STATUS_COLORS = [
    "--green",
    "--red",
    "--amber",
    "--blue",
    "--purple",
    "--slate",
]

EXPECTED_SHADOWS_AND_RADII = [
    "--shadow-sm",
    "--shadow-md",
    "--shadow-lg",
    "--r-sm",
    "--r-md",
    "--r-lg",
]


class TokensFileTests(SimpleTestCase):
    def test_tokens_file_exists_and_defines_roles(self):
        self.assertTrue(
            TOKENS_CSS.exists(),
            f"{TOKENS_CSS} должен существовать — единственный файл с "
            "hex-литералами в проекте.",
        )
        content = TOKENS_CSS.read_text(encoding="utf-8")
        for name in (
            EXPECTED_ROLES + EXPECTED_STATUS_COLORS + EXPECTED_SHADOWS_AND_RADII
        ):
            with self.subTest(token=name):
                self.assertIn(
                    f"{name}:",
                    content,
                    f"tokens.css не объявляет {name}",
                )


class SkeletonWiringTests(SimpleTestCase):
    def test_tokens_is_wired_before_custom_admin(self):
        self.assertTrue(
            SKELETON_HTML.exists(), f"{SKELETON_HTML} должен существовать"
        )
        content = SKELETON_HTML.read_text(encoding="utf-8")

        # Ищем позиции самих <link> тегов (href=...), а не любое
        # упоминание имени файла — оба имени фигурируют и в тексте
        # {% comment %}, который стоит раньше блока extrastyle.
        tokens_pos = content.find("href=\"{% static 'css/tokens.css'")
        custom_admin_pos = content.find(
            "href=\"{% static 'admin/css/custom_admin.css'"
        )

        self.assertNotEqual(
            tokens_pos, -1, "skeleton.html не подключает <link> на tokens.css"
        )
        self.assertNotEqual(
            custom_admin_pos,
            -1,
            "skeleton.html не подключает <link> на custom_admin.css",
        )
        self.assertLess(
            tokens_pos,
            custom_admin_pos,
            "tokens.css должен подключаться РАНЬШЕ custom_admin.css — "
            "иначе custom_admin.css не сможет опираться на роли токенов.",
        )


class NoRawHexOutsideTokensTests(SimpleTestCase):
    def test_no_raw_hex_outside_tokens(self):
        # На Task 2 список мигрированных файлов пуст — тест проходит
        # тривиально. Он растёт вместе с работой: каждая следующая задача
        # добавляет свой файл в MIGRATED_FILES ровно тогда, когда убирает
        # из него hex-литералы.
        for relative_path in MIGRATED_FILES:
            path = settings.BASE_DIR / relative_path
            with self.subTest(file=relative_path):
                self.assertTrue(path.exists(), f"{path} не существует")
                content = path.read_text(encoding="utf-8")
                matches = HEX_COLOR_RE.findall(content)
                self.assertFalse(
                    matches,
                    f"{relative_path} содержит hex-литералы вне tokens.css: "
                    f"{matches}",
                )

    def test_no_raw_rgb_outside_tokens(self):
        # claude — fix-round: closes the rgb()/rgba() loophole in the hex
        # check above. Scoped to RGB_STRICT_FILES, not MIGRATED_FILES — see
        # the comment on RGB_STRICT_FILES for why.
        for relative_path in RGB_STRICT_FILES:
            path = settings.BASE_DIR / relative_path
            with self.subTest(file=relative_path):
                self.assertTrue(path.exists(), f"{path} не существует")
                content = path.read_text(encoding="utf-8")
                matches = _non_exempt_rgb_matches(content)
                self.assertFalse(
                    matches,
                    f"{relative_path} содержит hardcoded rgb()/rgba() вне "
                    f"tokens.css (не pure-black): {matches}",
                )

    def test_grey_input_background_is_gone(self):
        # claude — #2a2a3d был тёмным фоном полей ввода custom_admin.css
        # (единственный цвет в проекте с фиолетовым подтоном, см. task-3-
        # brief.md и §1.1 спека). Task 3 переводит его на роль --input-bg;
        # величина должна исчезнуть из проекта целиком, а не просто из
        # одного файла — ищем по всему static/ и crm/.
        needle = "2a2a3d"
        # claude — этот тест-файл сам обязан упоминать needle текстом (выше
        # и в этой строке), иначе он совпадёт сам с собой при сканировании
        # crm/ — исключаем свой путь явно, а не потому что он "особенный".
        self_path = Path(__file__).resolve()
        hits = []
        for root_name in ("static", "crm"):
            root = settings.BASE_DIR / root_name
            for path in root.rglob("*"):
                if not path.is_file() or path.resolve() == self_path:
                    continue
                try:
                    content = path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, PermissionError):
                    continue
                if needle in content:
                    hits.append(str(path.relative_to(settings.BASE_DIR)))
        self.assertFalse(
            hits,
            f"Литерал {needle} всё ещё встречается: {hits}",
        )
