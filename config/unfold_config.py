from django.templatetags.static import static
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext_lazy as _

from crm.users.utils import user_has_perm

UNFOLD = {
    "SITE_TITLE": "Zetom CRM",
    "SITE_HEADER": "Zetom CRM",
    "SITE_SUBHEADER": "Control Panel",

# дропдаун сверху
    "SITE_DROPDOWN": [
        {
            "icon": "mail",
            "title": _("Email Form"),
            "link": reverse_lazy("zetom:index"),
        },
    ],

# дропдаун снизу
    "ACCOUNT": {
        "navigation": [
            {
                "title": _("View profile"),
                "link": lambda request: reverse(
                    "admin:auth_user_change",
                    args=[request.user.pk],
                ),
            },
        ],
    },

    "SITE_ICON": {
        "light": lambda request: static("img/icon.png"),
        "dark": lambda request: static("img/icon.png"),
    },
    "SITE_LOGO": {
        "light": lambda request: static("img/logo.avif"),
        "dark": lambda request: static("img/logo.avif"),
    },

    "LOGIN": {},

    # claude — глобальные ассеты Unfold-админки.
    # clickable_rows: клик по любой ячейке changelist открывает change-view.
    # notification_badge: polling /notifications/unread-count/ → бейдж в
    # sidebar/account-dropdown + префикс "(N) " в title вкладки.
    "STYLES": [
        lambda request: static("admin/css/clickable_rows.css"),
        lambda request: static("admin/css/notification_badge.css"),
    ],
    "SCRIPTS": [
        lambda request: static("admin/js/clickable_rows.js"),
        lambda request: static("admin/js/notification_badge.js"),
    ],

    "SITE_URL": "https://www.zetom.eu/",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,
    "SHOW_BACK_BUTTON": True,
    "SHOW_LANGUAGES": True,
    "BORDER_RADIUS": "6px",

    "COLORS": {
        "base": {
            "50": "oklch(98.5% .002 247.839)",
            "100": "oklch(96.7% .003 264.542)",
            "200": "oklch(92.8% .006 264.531)",
            "300": "oklch(87.2% .01 258.338)",
            "400": "oklch(70.7% .022 261.325)",
            "500": "oklch(55.1% .027 264.364)",
            "600": "oklch(44.6% .03 256.802)",
            "700": "oklch(37.3% .034 259.733)",
            "800": "oklch(27.8% .033 256.848)",
            "900": "oklch(21% .034 264.665)",
            "950": "oklch(13% .028 261.692)",
        },
        "primary": {
            "50": "oklch(98% .02 145)",
            "100": "oklch(94% .05 145)",
            "200": "oklch(88% .1 145)",
            "300": "oklch(80% .15 145)",
            "400": "oklch(70% .2 145)",
            "500": "oklch(60% .22 145)",
            "600": "oklch(50% .2 145)",
            "700": "oklch(42% .18 145)",
            "800": "oklch(35% .15 145)",
            "900": "oklch(28% .12 145)",
            "950": "oklch(20% .1 145)",
        },
        "font": {
            "subtle-light": "var(--color-base-500)",
            "subtle-dark": "var(--color-base-400)",
            "default-light": "var(--color-base-600)",
            "default-dark": "var(--color-base-300)",
            "important-light": "var(--color-base-900)",
            "important-dark": "var(--color-base-100)",
        },
    },

    "EXTENSIONS": {
        "modeltranslation": {
            "flags": {
                "en": "",
                "ru": "",
                "pl": "",
                "ua": "",
            },
        },
    },

    "SIDEBAR": {
        "show_search": True,
        "filter": "dcrm.unfold_sidebar.filter_sidebar_items",
        "navigation": [

            # claude — Inbox without a group, on top. No permission gate —
            # каждый staff юзер имеет inbox (в т.ч. system-нотификации).
            {
                "title": "Inbox",
                "collapsible": False,
                "items": [
                    {
                        "title": _("Inbox"),
                        "icon": "inbox",
                        "link": reverse_lazy("notification:inbox"),
                    },
                ],
            },

            # claude — рабочие сущности в порядке workflow: Null -> Main -> документы
            {
                "title": "Requests",
                "collapsible": True,
                "items": [
                    {
                        "title": _("Validation"),
                        "icon": "task_alt",
                        "link": reverse_lazy("admin:zetom_requestnull_changelist"),
                        "permission": lambda request: user_has_perm(
                            request.user, "view_requests"
                        ),
                    },
                    {
                        "title": _("Information"),
                        "icon": "folder",
                        "link": reverse_lazy("admin:zetom_requestmain_changelist"),
                        "permission": lambda request: user_has_perm(
                            request.user, "view_requests"
                        ),
                    },
                    {
                        "title": _("Offers"),
                        "icon": "request_quote",
                        "link": reverse_lazy("admin:zetom_oferta_changelist"),
                        "permission": lambda request: user_has_perm(
                            request.user, "view_requests"
                        ),
                    },
                    {
                        "title": _("Orders"),
                        "icon": "receipt_long",
                        "link": reverse_lazy("admin:zetom_zlecenie_changelist"),
                        "permission": lambda request: user_has_perm(
                            request.user, "view_requests"
                        ),
                    },
                    {
                        "title": _("Applications"),
                        "icon": "article",
                        "link": reverse_lazy("admin:zetom_wniosek_changelist"),
                        "permission": lambda request: user_has_perm(
                            request.user, "view_requests"
                        ),
                    },
                ],
            },

            # claude — терминальные/мусор. TODO[other dev]: Trash, возможно,
            # надо закрыть `delete_requests` отдельно. Пока — `view_requests`.
            {
                "title": "Archive",
                "collapsible": True,
                "items": [
                    {
                        "title": _("Cancelled"),
                        "icon": "cancel",
                        "link": reverse_lazy("admin:zetom_cancelledrequest_changelist"),
                        "permission": lambda request: user_has_perm(
                            request.user, "view_requests"
                        ),
                    },
                    {
                        "title": _("Trash"),
                        "icon": "delete",
                        "link": reverse_lazy("admin:zetom_deletedrequest_changelist"),
                        "permission": lambda request: user_has_perm(
                            request.user, "view_requests"
                        ),
                    },
                ],
            },

            {
                "title": "Clients",
                "collapsible": True,
                "items": [
                    {
                        "title": _("Clients"),
                        "icon": "business",
                        "link": reverse_lazy("admin:clients_client_changelist"),
                        "permission": lambda request: user_has_perm(
                            request.user, "view_clients"
                        ),
                    },
                ],
            },

            # claude — раньше "Admin"; переименовано в "Users & Access" чтобы
            # не путать с ролью admin и не вступать в конфликт с группой "System".
            {
                "title": "Users & Access",
                "collapsible": True,
                "items": [
                    {
                        "title": _("Users"),
                        "icon": "manage_accounts",
                        "link": reverse_lazy("admin:auth_user_changelist"),
                        "permission": lambda request: user_has_perm(
                            request.user, "view_users"
                        ),
                    },
                    {
                        "title": _("Roles"),
                        "icon": "shield",
                        "link": reverse_lazy("admin:users_role_changelist"),
                        "permission": lambda request: user_has_perm(
                            request.user, "view_roles"
                        ),
                    },
                ],
            },

            # claude — Системные / аудит логи. Гейты совпадают с теми, что
            # стоят на самих ModelAdmin'ах (LogEntryAdmin / NotificationAdmin /
            # EmailNotificationAdmin), иначе пункт сайдбара виден / скрыт
            # рассинхронно с реальным доступом.
            {
                "title": "System",
                "collapsible": True,
                "items": [
                    {
                        "title": _("Activity Log"),
                        "icon": "history",
                        "link": "/admin/admin/logentry/",
                        "permission": lambda request: user_has_perm(
                            request.user, "view_logs"
                        ),
                    },
                    {
                        "title": _("Notification log"),
                        "icon": "monitor_heart",
                        "link": reverse_lazy(
                            "admin:notification_notification_changelist"
                        ),
                        "permission": lambda request: user_has_perm(
                            request.user, "view_notification_log"
                        ),
                    },
                    {
                        "title": _("Email log"),
                        "icon": "outbox",
                        "link": reverse_lazy(
                            "admin:notification_emailnotification_changelist"
                        ),
                        "permission": lambda request: user_has_perm(
                            request.user, "view_email_log"
                        ),
                    },
                ],
            },
        ],
    },
}
