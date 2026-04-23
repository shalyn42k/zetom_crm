from django.templatetags.static import static
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

UNFOLD = {
    "SITE_TITLE": "Zetom CRM",
    "SITE_HEADER": "Zetom CRM",
    "SITE_SUBHEADER": "Control Panel",
    "SITE_DROPDOWN": [
        {
            "icon": "mail",
            "title": _("Email Form"),
            "link": reverse_lazy("zetom:index"),
        },
    ],
    # Static files
    "SITE_ICON": {  # чет не оч работает
        "light": lambda request: static("zetom/img/zet1.avif"),
        "dark": lambda request: static("zetom/img/zet1.avif"),
    },
    "SITE_LOGO": {
        "light": lambda request: static("zetom/img/logo.avif"),
        "dark": lambda request: static("zetom/img/logo.avif"),
    },
    "LOGIN": {
        # разобраться как красиво сделать бекграунд
        # "image": lambda request: static("zetom/img/bg.jpg"),
        # "redirect_after": lambda request: reverse_lazy("admin:APP_MODEL_changelist"),
        # Inherits from `unfold.forms.AuthenticationForm`
        # "form": "app.forms.CustomLoginForm",
    },
    "SITE_URL": "/",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,
    "SHOW_BACK_BUTTON": True,
    "SHOW_LANGUAGES": False,  # включить когда будет настроен перевод
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
        "navigation": [
            {
                "title": "Developer Interface",
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": "Valdiation Window",
                        "icon": "check",
                        "link": reverse_lazy("admin:zetom_requestnull_changelist"),
                    },
                    {
                        "title": "Activity Log",
                        "icon": "history",
                        "link": ("/admin/admin/logentry/"),
                    },
                    {
                        "title": "Notification",
                        "icon": "notifications",
                        "link": reverse_lazy(
                            "admin:notification_notification_changelist"
                        ),
                    },
                    {
                        "title": "Email Notification",
                        "icon": "notification_multiple",
                        "link": reverse_lazy(
                            "admin:notification_emailnotification_changelist"
                        ),
                    },
                ],
            },
            {
                "title": "Requests",  # название группы
                "separator": True,
                "collapsible": True,  # можно сворачивать
                "items": [
                    {
                        "title": "Information",
                        "icon": "folder",
                        "link": reverse_lazy("admin:zetom_requestmain_changelist"),
                    },
                    {
                        "title": "Oferta Information",
                        "icon": "description",
                        "link": reverse_lazy("admin:zetom_oferta_changelist"),
                    },
                    {
                        "title": "Zlecenie Information",
                        "icon": "description",
                        "link": reverse_lazy("admin:zetom_zlecenie_changelist"),
                    },
                    {
                        "title": "Wniosek Information",
                        "icon": "description",
                        "link": reverse_lazy("admin:zetom_wniosek_changelist"),
                    },
                ],
            },
            {
                "title": "Admin",
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": "Roles",
                        "icon": "shield",
                        "link": reverse_lazy("admin:users_role_changelist"),
                    },
                    {
                        "title": "Users",
                        "icon": "account_box",
                        "link": reverse_lazy("admin:users_userprofile_changelist"),
                    },
                ],
            },
        ],
    },
}
