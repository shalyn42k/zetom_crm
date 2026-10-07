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


# claude — fix-round (Task 5): RGB_LITERAL_RE was enforced only on the
# three files Task 5 owned — static/admin/css/custom_admin.css (Task 3) and
# static/clients/css/company_card.css / client_pages.css (Task 4) carried
# pre-existing non-exempt literal rgba() tints that predated this stricter
# check, named at the time as follow-up debt rather than fixed on the spot
# (out of Task 5's file scope).
#
# claude — Task 7 (final acceptance): that debt is paid off here.
# RGB_STRICT_FILES now covers all seven migrated files — the three above
# have had their non-exempt rgba() literals repointed at roles (see the
# per-rule comments in those files: custom_admin.css's #result_list
# striping and .crm-dashboard__* hero onto --slate/--color-base-N/
# --color-primary-N, company_card.css's modal scrim converged onto the
# pure-black exemption like validation_window.css's already was, and
# client_pages.css's spinner border onto the same white/color-mix idiom
# its own border-top-color already used) rather than by loosening this
# regex or shrinking the file list.
RGB_STRICT_FILES = [
    "static/admin/css/custom_admin.css",
    "static/clients/css/company_card.css",
    "static/clients/css/client_pages.css",
    "static/zetom/css/validation_window.css",
    "crm/zetom/static/zetom/css/email_form.css",
    "static/admin/css/notification_badge.css",
    "static/zetom/css/requestmain_detail.css",
]

# claude — Task 7: RGB_STRICT_FILES above now equals MIGRATED_FILES (every
# file that's ever been checked for hex is now also checked for rgb()).
# The three new checks below (hsl()/hsla(), literal oklch(), and named
# colours) reuse MIGRATED_FILES directly rather than introduce a fourth
# near-duplicate file list — there's no remaining scoping debt to track
# separately for them.

# claude — Task 7: hsl()/hsla() and literal oklch() slipped past both the
# hex check (not hex) and the rgb() check (not rgb) — the same
# "hardcoded pixels, different notation" bug in two more notations. oklch()
# is the important one: most of this codebase's non-hex colour already is
# oklch (Unfold's own --color-base-*/--color-primary-* scale resolves to
# oklch at runtime), so a literal oklch() is exactly as easy to slip in
# unnoticed as a literal hex was before Task 2. The tricky part is telling
# "var(--color-base-900), which happens to resolve to an oklch value" apart
# from "oklch(21% .034 264.665) typed out by hand" — only the source text
# matters here, and var(...) never contains the literal string "oklch(".
# Both regexes require a digit (or +/-) immediately after "(" and optional
# whitespace, which also means neither one accidentally matches this test
# file's own "oklch(...)" ellipsis or plain-English mentions of the syntax
# in code comments — those never start with a digit.
HSL_LITERAL_RE = re.compile(r"hsla?\(\s*-?\d[^)]*\)")
OKLCH_LITERAL_RE = re.compile(r"oklch\(\s*-?\d[^)]*\)")

# claude — Task 7 fix-round: static/css/tokens.css's roles now carry a
# var()-fallback hex, so email_form.css no longer needs to stay fully
# literal to survive rendering outside a ModelAdmin changeform — see that
# file's header comment for the full story. The 8 values that were an
# exact byte-for-byte match to both an Unfold base/primary-N step AND the
# specific role tokens.css assigns that same step (--zf-border/--zf-text/
# --zf-text-muted/--zf-text-subtle in light, --zf-surface/--zf-text/
# --zf-text-muted/--zf-text-subtle in dark, --zf-primary in light) were
# repointed at those roles and no longer appear here. What remains
# exempt is every value that has no exact-step role to repoint at —
# either the closest role sits on a *different* numeric step (dark
# --zf-border is base-800, tokens.css's --border role is base-700 — using
# it would silently shift this card's colour), or the hue (145 for
# --zf-primary-hover/--zf-primary-ring/--zf-notice-*, 25 for
# --zf-error-*) has no role at all. Scoped per-file (not a global value
# allowlist), so the same numbers appearing in some other file's literal
# oklch() would still be caught, and any *new* literal oklch() added to
# email_form.css beyond this known list would be too.
OKLCH_EXEMPT_BY_FILE = {
    "crm/zetom/static/zetom/css/email_form.css": {
        "oklch(27.8% .033 256.848)",
        "oklch(28% .12 145)",
        "oklch(28% .12 25)",
        "oklch(37.3% .034 259.733)",
        "oklch(42% .18 145)",
        "oklch(45% .2 25)",
        "oklch(60% .22 145)",
        "oklch(70% .2 145 / 0.35)",
        "oklch(70% .2 145)",
        "oklch(80% .15 145)",
        "oklch(80% .15 25)",
        "oklch(94% .05 145)",
        "oklch(94% .05 25)",
        "oklch(96% .03 25)",
    },
}


def _strip_comments(content):
    """Remove /* ... */ comments before scanning for named-colour usage.
    Unlike HEX_COLOR_RE/RGB_LITERAL_RE/HSL_LITERAL_RE/OKLCH_LITERAL_RE
    above (all kept scanning raw content, matching HEX/RGB's existing,
    already-shipped behaviour), a named-colour scan without this would
    flag ordinary English prose — these CSS files' own `claude —` comments
    talk about "green hue", "a red family", "drifted purple" etc.
    constantly, in ways that are much harder to reword around than the odd
    literal hex/rgb/oklch value quoted as an example."""
    return re.sub(r"/\*.*?\*/", "", content, flags=re.S)


# claude — Task 7: named CSS colour keywords beyond `white`/`black`, which
# this codebase already uses freely as universal keywords (see the
# HEX_COLOR_RE-era comments elsewhere in this file) and which this list
# deliberately excludes — flagging them would just force everyone to spell
# "white" as `var(--something)` for no reason. `transparent`, `currentColor`
# and `inherit` are not CSS named *colours* (they're separate keywords /
# computed values) and were never in this list to begin with, so they need
# no explicit exemption. The list itself is the full CSS Color Module
# extended-keyword set minus white/black.
NAMED_COLORS = [
    "aliceblue", "antiquewhite", "aqua", "aquamarine", "azure", "beige",
    "bisque", "blanchedalmond", "blueviolet", "brown", "burlywood",
    "cadetblue", "chartreuse", "chocolate", "coral", "cornflowerblue",
    "cornsilk", "crimson", "cyan", "darkblue", "darkcyan", "darkgoldenrod",
    "darkgray", "darkgreen", "darkgrey", "darkkhaki", "darkmagenta",
    "darkolivegreen", "darkorange", "darkorchid", "darkred", "darksalmon",
    "darkseagreen", "darkslateblue", "darkslategray", "darkslategrey",
    "darkturquoise", "darkviolet", "deeppink", "deepskyblue", "dimgray",
    "dimgrey", "dodgerblue", "firebrick", "floralwhite", "forestgreen",
    "fuchsia", "gainsboro", "ghostwhite", "gold", "goldenrod", "gray",
    "green", "greenyellow", "grey", "honeydew", "hotpink", "indianred",
    "indigo", "ivory", "khaki", "lavender", "lavenderblush", "lawngreen",
    "lemonchiffon", "lightblue", "lightcoral", "lightcyan",
    "lightgoldenrodyellow", "lightgray", "lightgreen", "lightgrey",
    "lightpink", "lightsalmon", "lightseagreen", "lightskyblue",
    "lightslategray", "lightslategrey", "lightsteelblue", "lightyellow",
    "lime", "limegreen", "linen", "magenta", "maroon", "mediumaquamarine",
    "mediumblue", "mediumorchid", "mediumpurple", "mediumseagreen",
    "mediumslateblue", "mediumspringgreen", "mediumturquoise",
    "mediumvioletred", "midnightblue", "mintcream", "mistyrose", "moccasin",
    "navajowhite", "navy", "oldlace", "olive", "olivedrab", "orange",
    "orangered", "orchid", "palegoldenrod", "palegreen", "paleturquoise",
    "palevioletred", "papayawhip", "peachpuff", "peru", "pink", "plum",
    "powderblue", "purple", "rebeccapurple", "red", "rosybrown",
    "royalblue", "saddlebrown", "salmon", "sandybrown", "seagreen",
    "seashell", "sienna", "silver", "skyblue", "slateblue", "slategray",
    "slategrey", "snow", "springgreen", "steelblue", "tan", "teal",
    "thistle", "tomato", "turquoise", "violet", "wheat", "whitesmoke",
    "yellow", "yellowgreen",
]

# claude — Task 7: matches a named colour only where it's used as a value
# (preceded/followed by punctuation or whitespace), not as a fragment of an
# identifier. (?<![\w.#-]) rejects a match preceded by a word character, a
# dot (class selector, e.g. `.green-badge`), a hash (id selector) or a
# hyphen — that last one is what keeps this from matching "green" inside
# `--green` or `var(--green-bright)`: CSS custom property names and
# multi-word idents use `-` as a separator, and `\b` alone treats `-` as a
# boundary, so a plain \bgreen\b would wrongly fire on `--green`. Mirrored
# on the right with (?![\w-]) so "greenyellow" doesn't also register a
# spurious "green" hit.
NAMED_COLOR_RE = re.compile(
    r"(?<![\w.#-])(" + "|".join(NAMED_COLORS) + r")(?![\w-])",
    re.IGNORECASE,
)

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

    def test_no_raw_hsl_outside_tokens(self):
        # claude — Task 7: hsl()/hsla() with literal numeric channels — the
        # same class of bug as raw hex/rgb(), just a notation nobody had
        # happened to use yet in these seven files (confirmed empty below,
        # not "presumed empty" — see test_hsl_regex_detects_a_real_literal
        # for proof the regex isn't just trivially passing).
        for relative_path in MIGRATED_FILES:
            path = settings.BASE_DIR / relative_path
            with self.subTest(file=relative_path):
                self.assertTrue(path.exists(), f"{path} не существует")
                content = path.read_text(encoding="utf-8")
                matches = HSL_LITERAL_RE.findall(content)
                self.assertFalse(
                    matches,
                    f"{relative_path} содержит literal hsl()/hsla(): "
                    f"{matches}",
                )

    def test_no_raw_oklch_outside_tokens(self):
        # claude — Task 7: literal oklch() — see the OKLCH_LITERAL_RE and
        # OKLCH_EXEMPT_BY_FILE comments above for what this catches and the
        # one deliberate, per-file exemption (email_form.css's whole
        # --zf-* palette — that page can't consume var(--color-base-N)/
        # var(--color-primary-N) at all, confirmed live, so its colours
        # have to stay genuinely self-sufficient literals).
        for relative_path in MIGRATED_FILES:
            path = settings.BASE_DIR / relative_path
            with self.subTest(file=relative_path):
                self.assertTrue(path.exists(), f"{path} не существует")
                content = path.read_text(encoding="utf-8")
                exempt = OKLCH_EXEMPT_BY_FILE.get(relative_path, set())
                matches = [
                    m for m in OKLCH_LITERAL_RE.findall(content)
                    if m not in exempt
                ]
                self.assertFalse(
                    matches,
                    f"{relative_path} содержит literal oklch() вне "
                    f"tokens.css: {matches}",
                )

    def test_no_named_colors_outside_tokens(self):
        # claude — Task 7: named CSS colours beyond white/black — see
        # NAMED_COLOR_RE's comment above for the identifier/selector
        # false-positive guard and why comments are stripped first.
        for relative_path in MIGRATED_FILES:
            path = settings.BASE_DIR / relative_path
            with self.subTest(file=relative_path):
                self.assertTrue(path.exists(), f"{path} не существует")
                content = _strip_comments(path.read_text(encoding="utf-8"))
                matches = NAMED_COLOR_RE.findall(content)
                self.assertFalse(
                    matches,
                    f"{relative_path} содержит именованные CSS-цвета вне "
                    f"white/black: {matches}",
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


class NewDetectorsCanActuallyFailTests(SimpleTestCase):
    """claude — Task 7: "prove each new detector can fail before you rely
    on it" (task-7-brief addition 2). All seven migrated files are clean
    of hsl()/literal-oklch()/named-colours right now, which means the
    three tests above pass whether or not their regexes actually work — a
    regex that matched nothing at all would pass exactly as green. These
    tests feed each new regex a minimal fixture string that a legacy CSS
    file plausibly could have contained, and assert it DOES match — so a
    future accidental loosening of the regex (e.g. dropping the `-?\\d`
    anchor, or the identifier guard) fails loudly here instead of silently
    passing everything upstream."""

    def test_hsl_regex_detects_a_real_literal(self):
        fixture = ".legacy { background: hsl(210, 60%, 50%); }"
        self.assertTrue(
            HSL_LITERAL_RE.search(fixture),
            "HSL_LITERAL_RE не поймал явный hsl() литерал — "
            "детектор не работает",
        )
        # var()-based usage must NOT be flagged — only literals are.
        self.assertFalse(
            HSL_LITERAL_RE.search(".ok { color: hsl(var(--h) 60% 50%); }"),
            "HSL_LITERAL_RE ложно сработал на var()-based hsl()",
        )

    def test_oklch_regex_detects_a_real_literal(self):
        fixture = ".legacy { color: oklch(55.1% .027 264.364); }"
        self.assertTrue(
            OKLCH_LITERAL_RE.search(fixture),
            "OKLCH_LITERAL_RE не поймал явный oklch() литерал — "
            "детектор не работает",
        )
        # var(--color-base-900) resolves to oklch at runtime but must NOT
        # be flagged — the regex only cares about the source text.
        self.assertFalse(
            OKLCH_LITERAL_RE.search(".ok { color: var(--color-base-900); }"),
            "OKLCH_LITERAL_RE ложно сработал на var(--color-base-900)",
        )
        # A prose mention of the syntax (no leading digit) must not match
        # either — this is what keeps this test file's and the migrated
        # files' own comments from tripping the check on themselves.
        self.assertFalse(
            OKLCH_LITERAL_RE.search("/* colours are oklch(...) now */"),
            "OKLCH_LITERAL_RE ложно сработал на прозу 'oklch(...)'",
        )

    def test_named_color_regex_detects_a_real_literal(self):
        fixture = ".legacy { border-color: indigo; }"
        self.assertTrue(
            NAMED_COLOR_RE.search(fixture),
            "NAMED_COLOR_RE не поймал явный именованный цвет — "
            "детектор не работает",
        )
        # white/black are tolerated by convention — not flagged.
        self.assertFalse(
            NAMED_COLOR_RE.search(".ok { color: white; background: black; }"),
            "NAMED_COLOR_RE ложно сработал на white/black",
        )
        # Custom-property and class-name fragments must not be flagged —
        # this is the false positive that would otherwise fire on every
        # var(--green)/.green-badge in the migrated files.
        self.assertFalse(
            NAMED_COLOR_RE.search(".green-badge { color: var(--green-bright); }"),
            "NAMED_COLOR_RE ложно сработал на --green/.green-badge",
        )
