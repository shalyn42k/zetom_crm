"""Read-only viewer for django.contrib.admin.LogEntry."""
from django.contrib import admin
from django.contrib.admin.models import LogEntry
from unfold.admin import ModelAdmin


@admin.register(LogEntry)
class LogEntryAdmin(ModelAdmin):
    list_display = ("action_time", "user", "content_type", "object_repr", "action_flag")
    list_filter = ("action_flag", "content_type", "user")
    search_fields = ("object_repr", "change_message")

    def has_view_permission(self, request, obj=None):
        return True

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
