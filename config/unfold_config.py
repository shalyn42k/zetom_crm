from django.templatetags.static import static
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext_lazy as _

from crm.notification.utils import unread_count
from crm.users.utils import user_has_perm


# claude — формат строки "Notifications (3)" / "Notifications" для ACCOUNT dropdown
def _notifications_title(request):
    count = unread_count(getattr(request, "user", None))
    base = _("Notifications")
    return f"{base} ({count})" if count else base


# claude — link на changelist Notification, отфильтрованный по recipient=user и непрочитанным
def _notifications_link(request):
    base = reverse("admin:notification_notification_changelist")
    user_id = getattr(getattr(request, "user", None), "id", None)
    if user_id is None:
        return base
    return f"{base}?recipient__id__exact={user_id}&is_read__exact=0"

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
            # claude
            {
                "title": _notifications_title,
                "link": _notifications_link,
                "icon": "notifications",
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

            {
                "title": "Developer Interface",
                "collapsible": True,
                "items": [
                    {
                        "title": "Validation Window",
                        "icon": "check",
                        "link": reverse_lazy("admin:zetom_requestnull_changelist"),
                        "permission": lambda request: user_has_perm(
                            request.user, "view_requests"
                        ),
                    },
                    {
                        "title": "Activity Log",
                        "icon": "history",
                        "link": "/admin/admin/logentry/",
                        "permission": lambda request: user_has_perm(
                            request.user, "view_admin_panel"
                        ),
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
                "title": "Clients",
                "collapsible": True,
                "items": [
                    {
                        "title": "Clients",
                        "icon": "account_circle",
                        "link": reverse_lazy("admin:clients_client_changelist"),
                        "permission": lambda request: user_has_perm(
                            request.user, "view_clients"
                        ),
                    },
                ],
            },

            {
                "title": "Requests",
                "collapsible": True,
                "items": [
                    {
                        "title": "Trash",
                        "icon": "delete",
                        "link": reverse_lazy("admin:zetom_deletedrequest_changelist"),
                        "permission": lambda request: user_has_perm(
                            request.user, "view_requests"
                        ),
                    },


                    {
                        "title": "Cancelled",
                        "icon": "cancel",
                        "link": reverse_lazy("admin:zetom_cancelledrequest_changelist"),
                        "permission": lambda request: user_has_perm(
                           request.user, "view_requests"
                        ),
                    },

                    {
                        "title": "Information",
                        "icon": "folder",
                        "link": reverse_lazy("admin:zetom_requestmain_changelist"),
                        "permission": lambda request: user_has_perm(
                            request.user, "view_requests"
                        ),
                    },
                    {
                        "title": "Offers",
                        "icon": "description",
                        "link": reverse_lazy("admin:zetom_oferta_changelist"),
                        "permission": lambda request: user_has_perm(
                            request.user, "view_requests"
                        ),
                    },
                    {
                        "title": "Orders",
                        "icon": "description",
                        "link": reverse_lazy("admin:zetom_zlecenie_changelist"),
                    },
                    {
                        "title": "Applications",
                        "icon": "description",
                        "link": reverse_lazy("admin:zetom_wniosek_changelist"),
                    },
                ],
            },

            {
                "title": "Admin",
                "collapsible": True,
                "items": [
                    {
                        "title": "Roles",
                        "icon": "shield",
                        "link": reverse_lazy("admin:users_role_changelist"),
                        "permission": lambda request: user_has_perm(
                            request.user, "view_roles"
                        ),
                    },
                    {
                        "title": "Users",
                        "icon": "account_box",
                        "link": reverse_lazy("admin:auth_user_changelist"),
                        "permission": lambda request: user_has_perm(
                            request.user, "view_users"
                        ),
                    },
                ],
            },
        ],
    },
}
