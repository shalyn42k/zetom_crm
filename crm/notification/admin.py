from django.contrib import admin
from unfold.admin import ModelAdmin

from crm.notification.models import EmailNotification, Notification


# claude
@admin.register(Notification)
class NotificationAdmin(ModelAdmin):
    list_display = ("created_at", "kind", "recipient", "template_name", "is_read")
    list_filter = ("kind", "is_read", "created_at")
    search_fields = ("recipient__username", "recipient__email", "template_name")
    readonly_fields = (
        "recipient", "actor", "kind", "template_name", "payload",
        "target_content_type", "target_object_id",
        "is_read", "read_at", "created_at",
    )
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# claude
@admin.register(EmailNotification)
class EmailNotificationAdmin(ModelAdmin):
    list_display = ("created_at", "recipient_email", "subject", "status", "sent_at")
    list_filter = ("status", "created_at")
    search_fields = ("recipient_email", "subject", "template_name")
    readonly_fields = (
        "recipient_email", "actor", "template_name", "subject", "payload",
        "status", "status_reason", "sent_at", "created_at",
    )
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
