"""Read-only viewer for django.contrib.admin.LogEntry (Activity Log)."""
from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin

from crm.users.utils import user_has_perm


@admin.register(LogEntry)
class LogEntryAdmin(ModelAdmin):
    list_display = ("action_time", "user", "content_type", "object_repr", "action_flag")
    list_filter = ("action_flag", "content_type", "user")
    search_fields = ("object_repr", "change_message")

    # claude — no `fields`/`readonly_fields` here before meant the change
    # view fell back to every model field in its raw form; for
    # `change_message` that's the literal JSON Django stores
    # (e.g. `[{"added": {}}]`), not the sentence a human reads elsewhere
    # (list views, the dashboard's recent-activity feed) via
    # LogEntry.get_change_message(). Swaps the raw field for that.
    fields = readonly_fields = (
        "action_time", "user", "content_type", "object_id",
        "object_repr", "action_flag", "change_message_display",
    )

    @admin.display(description=_("Change message"))
    def change_message_display(self, obj):
        return obj.get_change_message()

    # claude — Activity log = system-wide who-changed-what. Раньше `True`
    # без условий: любой is_staff видел все правки. Теперь гейтим
    # permission'ом `view_logs` (см. crm/users/signals.py). add/change/delete
    # остаются запрещёнными всем — это immutable аудит.
    def has_module_permission(self, request):
        return user_has_perm(request.user, "view_logs")

    def has_view_permission(self, request, obj=None):
        return user_has_perm(request.user, "view_logs")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
