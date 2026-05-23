# Django imports
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from crm.users.models import User


class NotificationKind(models.TextChoices):
    STATUS_CHANGE = "STATUS_CHANGE", "Status change"
    REVIEW_REQUEST = "REVIEW_REQUEST", "Review request"
    REVIEW_RESOLVED = "REVIEW_RESOLVED", "Review resolved"
    ASSIGNMENT = "ASSIGNMENT", "Assignment"
    SYSTEM = "SYSTEM", "System"


class EmailStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    SENT = "SENT", "Sent"
    FAILED = "FAILED", "Failed"


class EmailNotification(models.Model):
    recipient_email = models.EmailField(max_length=254)
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_emails",
    )
    template_name = models.CharField(max_length=255)
    subject = models.CharField(max_length=255)
    payload = models.JSONField(default=dict)
    status = models.CharField(
        max_length=20,
        choices=EmailStatus.choices,
        default=EmailStatus.PENDING,
    )
    status_reason = models.TextField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Notification(models.Model):
    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="inapp_notifications",
    )
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acted_inapp_notifications",
    )
    kind = models.CharField(max_length=32, choices=NotificationKind.choices)
    template_name = models.CharField(max_length=255)
    payload = models.JSONField(
        default=dict,
        help_text="Data to replace template placeholders.",
    )
    target_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    target_object_id = models.PositiveIntegerField(null=True, blank=True)
    target = GenericForeignKey("target_content_type", "target_object_id")
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # claude
    class Meta:
        indexes = [
            models.Index(fields=["recipient", "is_read"]),
            models.Index(fields=["recipient", "-created_at"]),
        ]
