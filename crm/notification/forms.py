# claude
"""Compose form for ScheduledMessage — one form for client emails, messages
to colleagues and role broadcasts. Choices depend on who is writing and on
the document it is attached to, so the form takes both in its constructor."""
from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from crm.notification import message_targets
from crm.notification.models import MessageAudience, MessageChannel
from crm.notification.services.preferences import PREFERENCE_FIELDS


class MessageComposeForm(forms.Form):
    audience = forms.ChoiceField(label=_("To"))
    channel = forms.ChoiceField(
        label=_("Channel"), choices=MessageChannel.choices, initial=MessageChannel.INAPP, required=False,
    )
    client_email = forms.ChoiceField(label=_("Client email"), required=False)
    users = forms.ModelMultipleChoiceField(label=_("Users"), queryset=None, required=False)
    roles = forms.MultipleChoiceField(label=_("Roles"), required=False)
    subject = forms.CharField(label=_("Subject"), max_length=255)
    body = forms.CharField(label=_("Message"), widget=forms.Textarea(attrs={"rows": 5}))
    send_at = forms.DateTimeField(
        label=_("Send at"),
        required=False,
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"],
        help_text=_("Leave empty to send now."),
    )

    def __init__(self, *args, user, target, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.target = target
        allowed = set(message_targets.allowed_audiences(user))
        self.fields["audience"].choices = [c for c in MessageAudience.choices if c[0] in allowed]
        self.fields["client_email"].choices = [(e, e) for e in message_targets.client_email_choices(target)]
        self.fields["users"].queryset = message_targets.staff_user_choices(user)
        self.fields["roles"].choices = message_targets.role_choices()

    def clean_send_at(self):
        send_at = self.cleaned_data.get("send_at")
        if send_at and send_at < timezone.now() - timezone.timedelta(minutes=1):
            raise forms.ValidationError(_("Pick a time in the future, or leave it empty to send now."))
        return send_at

    def clean(self):
        data = super().clean()
        audience = data.get("audience")
        if audience == MessageAudience.CLIENT and not data.get("client_email"):
            self.add_error("client_email", _("This document has no client email."))
        if audience == MessageAudience.USERS and not data.get("users"):
            self.add_error("users", _("Choose at least one user."))
        if audience == MessageAudience.ROLES and not data.get("roles"):
            self.add_error("roles", _("Choose at least one role."))
        if not data.get("channel"):
            data["channel"] = MessageChannel.INAPP
        return data


class NotificationPreferenceForm(forms.Form):
    """Plain checkbox form over preferences.PREFERENCE_FIELDS."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in PREFERENCE_FIELDS:
            self.fields[name] = forms.BooleanField(required=False)
