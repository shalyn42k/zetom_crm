# Django imports
from django.db import models
from users.models import User

class NotificationTemplate(models.Model):
    title = models.CharField(max_length=255)
    template = models.TextField(help_text='Use placeholders like {{username}} for personalization.')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class ChannelType(models.TextChoices):
    APP = 'APP', 'In-App Notification'
    EMAIL = 'EMAIL', 'Email'


class StatusType(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    SUCCESS = 'SUCCESS', 'Success'
    FAILED = 'FAILED', 'Failed'

class EmailNotification(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='email_notifications')
    content = models.ForeignKey(NotificationTemplate, on_delete=models.CASCADE, related_name='email_notifications')
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=StatusType.choices, default=StatusType.PENDING)
    status_reason = models.TextField(null=True)

    @property
    def email_content(self):
        """
        Populate the template with dynamic data from the payload.
        """
        content = self.content.template
        for key, value in self.payload.items():
            content = re.sub(
                rf"{{{{\s*{key}\s*}}}}",
                str(value),
                content,
            )
        return content

class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    content = models.ForeignKey(NotificationTemplate, on_delete=models.CASCADE, related_name="notifications")
    payload = models.JSONField(default=dict, help_text="Data to replace template placeholders.")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)   
