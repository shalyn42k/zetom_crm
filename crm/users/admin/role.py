from django.contrib import admin
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin as UnfoldModelAdmin

from crm.users.models import Role
from crm.users.utils import user_has_perm


@admin.register(Role)
class AdminRole(UnfoldModelAdmin):
    # claude — Fix-round: the list used to show only code/name, so the one
    # question this page actually exists to answer — "what can this role
    # do" — needed a click into a change form that's disabled anyway
    # (has_change_permission is False; rows aren't even links, see
    # get_list_display_links below). permissions_display renders each
    # role's Permission set right in the row.
    list_display = ("code", "name", "permissions_display")

    def has_view_permission(self, request, obj=None):
        return user_has_perm(request.user, "view_roles")

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_list_display_links(self, request, list_display):
        return None

    def get_queryset(self, request):
        # claude — avoids one .permissions query per row (N+1) for
        # permissions_display below.
        return super().get_queryset(request).prefetch_related("permissions")

    # claude — Fix-round: first attempt styled the chips with an explicit
    # light-mode background + a `dark:!bg-...` Tailwind class for dark
    # mode. Dropped that — Tailwind's CSS here is a precompiled bundle
    # built by scanning template/source files for literal class strings;
    # a class only assembled at runtime inside format_html (never written
    # out anywhere the scanner reads) has no matching rule in that bundle
    # and silently does nothing (this bit twice already this session, see
    # the company_card.css fix-round commits — not guessing again).
    # `color: inherit` + a translucent neutral background sidesteps the
    # whole light/dark-token question: no CSS variable lookup, no
    # Tailwind class, reads fine on both surfaces without a dark-mode
    # branch to get wrong.
    @admin.display(description=_("Permissions"))
    def permissions_display(self, obj):
        names = sorted(p.name for p in obj.permissions.all())
        if not names:
            return "—"
        return format_html(
            '<div style="display:flex;flex-wrap:wrap;gap:4px 6px;max-width:520px">{}</div>',
            format_html_join(
                "",
                '<span style="display:inline-block;padding:2px 8px;border-radius:999px;'
                'font-size:12px;line-height:1.6;background:rgba(127,127,127,.18);'
                'color:inherit">{}</span>',
                ((name,) for name in names),
            ),
        )
