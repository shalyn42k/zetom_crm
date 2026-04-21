from django.contrib import admin
from unfold.admin import ModelAdmin


from notification.models import Notification, EmailNotification

@admin.register(Notification)
class NotificationAdmin(ModelAdmin):
    list_display = ("created_at", "user")


@admin.register(EmailNotification)
class EmailNotificationAdmin(ModelAdmin):
    list_display = ["created_at", "user"]
