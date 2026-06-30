# Django imports
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _

from crm.users.models import User


class NotificationKind(models.TextChoices):
    STATUS_CHANGE = "STATUS_CHANGE", _("Status change")
    REVIEW_REQUEST = "REVIEW_REQUEST", _("Review request")
    REVIEW_RESOLVED = "REVIEW_RESOLVED", _("Review resolved")
    ASSIGNMENT = "ASSIGNMENT", _("Assignment")
    SYSTEM = "SYSTEM", _("System")


class EmailStatus(models.TextChoices):
    PENDING = "PENDING", _("Pending")
    SENT = "SENT", _("Sent")
    FAILED = "FAILED", _("Failed")


class EmailNotification(models.Model):
    recipient_email = models.EmailField(max_length=254, verbose_name=_("Recipient email"))
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_emails",
        verbose_name=_("Actor"),
    )
    template_name = models.CharField(max_length=255, verbose_name=_("Template name"))
    subject = models.CharField(max_length=255, verbose_name=_("Subject"))
    payload = models.JSONField(default=dict, verbose_name=_("Payload"))
    status = models.CharField(
        max_length=20,
        choices=EmailStatus.choices,
        default=EmailStatus.PENDING,
        verbose_name=_("Status"),
    )
    status_reason = models.TextField(null=True, blank=True, verbose_name=_("Status reason"))
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Sent at"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))

    # claude
    def __str__(self):
        when = self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else "—"
        return f"[{self.status}] {self.subject or '(no subject)'} → {self.recipient_email} · {when}"


class Notification(models.Model):
    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="inapp_notifications",
        verbose_name=_("Recipient"),
    )
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acted_inapp_notifications",
        verbose_name=_("Actor"),
    )
    kind = models.CharField(max_length=32, choices=NotificationKind.choices, verbose_name=_("Kind"))
    template_name = models.CharField(max_length=255, verbose_name=_("Template name"))
    payload = models.JSONField(
        default=dict,
        verbose_name=_("Payload"),
        help_text=_("Data to replace template placeholders."),
    )
    target_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Target content type"),
    )
    target_object_id = models.PositiveIntegerField(null=True, blank=True, verbose_name=_("Target object id"))
    target = GenericForeignKey("target_content_type", "target_object_id")
    is_read = models.BooleanField(default=False, verbose_name=_("Is read"))
    read_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Read at"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))

    # claude
    class Meta:
        indexes = [
            models.Index(fields=["recipient", "is_read"]),
            models.Index(fields=["recipient", "-created_at"]),
        ]

    # claude
    def __str__(self):
        kind_label = NotificationKind(self.kind).label if self.kind in NotificationKind.values else self.kind
        actor = self.actor.get_username() if self.actor_id else "system"
        when = self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else "—"
        return f"{kind_label} · {actor} → {self.recipient.get_username()} · {when}"
