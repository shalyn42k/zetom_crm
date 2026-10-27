# Django imports
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils.translation import gettext_lazy as _, pgettext_lazy

from crm.users.models import User


class NotificationKind(models.TextChoices):
    STATUS_CHANGE = "STATUS_CHANGE", _("Status change")
    REVIEW_REQUEST = "REVIEW_REQUEST", _("Review request")
    REVIEW_RESOLVED = "REVIEW_RESOLVED", _("Review resolved")
    ASSIGNMENT = "ASSIGNMENT", _("Assignment")
    SYSTEM = "SYSTEM", _("System")
    # claude — reminders (follow-up dates, stale requests) and messages one
    # staff member sends to others (ScheduledMessage) get their own kinds so
    # the inbox can filter them and NotificationPreference can mute them.
    REMINDER = "REMINDER", _("Reminder")
    MESSAGE = "MESSAGE", _("Message")


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

    class Meta:
        verbose_name = _("Email notification")
        verbose_name_plural = _("Email notifications")

    # claude
    def __str__(self):
        when = self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else "—"
        # claude — was self.status (the raw EmailStatus code, e.g. "FAILED"),
        # not its translated label; get_status_display() resolves through
        # the choices' _() labels at render time.
        subject = self.subject or str(_("(no subject)"))
        return f"[{self.get_status_display()}] {subject} → {self.recipient_email} · {when}"


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
        verbose_name = _("Notification")
        verbose_name_plural = _("Notifications")
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


# claude
class NotificationPreference(models.Model):
    """Per-user switches for the notifications that can be muted.

    No row means "all defaults" — preferences.get_preferences() returns an
    unsaved instance in that case, so the send pipeline never has to create
    rows just to read them. Review requests/resolutions and system events
    are deliberately not here: they require action, muting them would
    silently break the review flow.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="notification_preference",
        verbose_name=_("User"),
    )
    inapp_assignment = models.BooleanField(default=True, verbose_name=_("Assigned to a request"))
    inapp_status_change = models.BooleanField(default=True, verbose_name=_("Request status changed"))
    inapp_reminders = models.BooleanField(default=True, verbose_name=_("Reminders in the inbox"))
    inapp_messages = models.BooleanField(default=True, verbose_name=_("Messages in the inbox"))
    email_reminders = models.BooleanField(default=False, verbose_name=_("Reminders by email"))
    email_messages = models.BooleanField(default=True, verbose_name=_("Messages by email"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated at"))

    class Meta:
        verbose_name = _("Notification preference")
        verbose_name_plural = _("Notification preferences")

    def __str__(self):
        return str(_("Notification preferences: %(user)s") % {"user": self.user.get_username()})


# claude
class MessageAudience(models.TextChoices):
    CLIENT = "CLIENT", _("Client")
    USERS = "USERS", _("Selected users")
    ROLES = "ROLES", _("Roles")


# claude
class MessageChannel(models.TextChoices):
    INAPP = "INAPP", _("Inbox")
    EMAIL = "EMAIL", _("Email")
    BOTH = "BOTH", _("Inbox and email")


# claude
class MessageStatus(models.TextChoices):
    # Context keeps these apart from EmailStatus' "Sent"/"Failed": in Polish a
    # message (wiadomość) is feminine, an email is masculine.
    PENDING = "PENDING", pgettext_lazy("message status", "Scheduled")
    SENT = "SENT", pgettext_lazy("message status", "Sent")
    CANCELLED = "CANCELLED", pgettext_lazy("message status", "Cancelled")
    FAILED = "FAILED", pgettext_lazy("message status", "Failed")


# claude
class ScheduledMessage(models.Model):
    """A message or reminder written by a staff member, sent now or later.

    One model covers the three cases the CRM needs: an email reminder to the
    client, a reminder/message to chosen colleagues, and a broadcast to every
    user holding some role(s). `send_at` in the past or now means "send
    immediately"; otherwise the followup scheduler tick picks it up — see
    services/scheduled_messages.process_due_messages.
    """

    author = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scheduled_messages",
        verbose_name=_("Author"),
    )
    audience = models.CharField(max_length=10, choices=MessageAudience.choices, verbose_name=_("Recipients"))
    channel = models.CharField(
        max_length=10,
        choices=MessageChannel.choices,
        default=MessageChannel.INAPP,
        verbose_name=_("Channel"),
    )
    recipient_users = models.ManyToManyField(
        User,
        blank=True,
        related_name="received_scheduled_messages",
        verbose_name=_("Users"),
    )
    recipient_roles = ArrayField(
        models.CharField(max_length=50),
        default=list,
        blank=True,
        verbose_name=_("Roles"),
    )
    client_email = models.EmailField(max_length=254, blank=True, verbose_name=_("Client email"))
    subject = models.CharField(max_length=255, verbose_name=_("Subject"))
    body = models.TextField(verbose_name=_("Message"))
    send_at = models.DateTimeField(verbose_name=_("Send at"))
    status = models.CharField(
        max_length=10,
        choices=MessageStatus.choices,
        default=MessageStatus.PENDING,
        verbose_name=_("Status"),
    )
    status_reason = models.TextField(blank=True, verbose_name=_("Status reason"))
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Sent at"))
    recipients_count = models.PositiveIntegerField(default=0, verbose_name=_("Recipients count"))
    target_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Target content type"),
    )
    target_object_id = models.PositiveIntegerField(null=True, blank=True, verbose_name=_("Target object id"))
    target = GenericForeignKey("target_content_type", "target_object_id")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))

    class Meta:
        verbose_name = _("Scheduled message")
        verbose_name_plural = _("Scheduled messages")
        ordering = ["-send_at"]
        indexes = [
            models.Index(fields=["status", "send_at"]),
            models.Index(fields=["target_content_type", "target_object_id"]),
        ]

    def __str__(self):
        return f"[{self.get_status_display()}] {self.subject}"
