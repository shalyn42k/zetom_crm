from django.contrib import admin
from unfold.admin import ModelAdmin

from crm.notification.models import EmailNotification, Notification

from crm.zetom.admin import BaseRequestAdmin

@admin.register(Notification)
class NotificationAdmin(BaseRequestAdmin):
    list_display = ("created_at", "user")


@admin.register(EmailNotification)
class EmailNotificationAdmin(BaseRequestAdmin):
    list_display = ["created_at", "user"]
