# claude
"""POST endpoints for the message composer (document window) and the
notification settings (own page + admin's user tab)."""
from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import formats, timezone
from django.utils.translation import gettext, gettext_lazy as _
from django.views.decorators.http import require_POST

from crm.notification import message_targets
from crm.notification.forms import MessageComposeForm
from crm.notification.models import (
    MessageAudience, MessageStatus, ScheduledMessage,
)
from crm.notification.services import preferences, scheduled_messages
from crm.users.utils import user_has_perm

User = get_user_model()

_AUDIENCE_PERM = {
    MessageAudience.CLIENT: "send_client_messages",
    MessageAudience.USERS: "send_staff_messages",
    MessageAudience.ROLES: "message_roles",
}


def _target_url(target):
    opts = target._meta
    return reverse(f"admin:{opts.app_label}_{opts.model_name}_change", args=[target.pk]) + "#messages"


@require_POST
@staff_member_required
def compose(request):
    target = message_targets.resolve_target(request.user, request.POST.get("target"))
    if target is None:
        raise Http404

    form = MessageComposeForm(request.POST, user=request.user, target=target)
    if not form.is_valid():
        # Re-check the raw audience first: an audience the user may not use
        # is dropped from the choices, so it shows up as a form error too.
        audience = request.POST.get("audience")
        perm = _AUDIENCE_PERM.get(audience)
        if perm and not user_has_perm(request.user, perm):
            return HttpResponseForbidden(gettext("You don't have permission for this action."))
        for field, errors in form.errors.items():
            label = form.fields[field].label if field in form.fields else ""
            for error in errors:
                messages.error(request, f"{label}: {error}" if label else error)
        return redirect(_target_url(target))

    data = form.cleaned_data
    message = scheduled_messages.schedule_message(
        author=request.user,
        audience=data["audience"],
        channel=data["channel"],
        subject=data["subject"],
        body=data["body"],
        send_at=data.get("send_at"),
        users=data.get("users") or (),
        roles=data.get("roles") or (),
        client_email=data.get("client_email") or "",
        target=target,
    )
    if message.status == MessageStatus.SENT:
        messages.success(
            request,
            _("Message sent (%(count)s recipient(s)).") % {"count": message.recipients_count},
        )
    elif message.status == MessageStatus.PENDING:
        when = formats.date_format(timezone.localtime(message.send_at), "DATETIME_FORMAT")
        messages.success(request, _("Message scheduled for %(when)s.") % {"when": when})
    else:
        messages.warning(request, _("The message could not be delivered to anyone."))
    return redirect(_target_url(target))


@require_POST
@staff_member_required
def cancel(request, pk):
    message = get_object_or_404(ScheduledMessage, pk=pk)
    target = message.target
    # Visibility of the document also gates the cancel: an author who lost
    # access to the request can no longer touch messages attached to it.
    if target is not None and message_targets.resolve_target(
        request.user, message_targets.target_key(target)
    ) is None:
        raise Http404
    if not message_targets.can_cancel(request.user, message):
        return HttpResponseForbidden(gettext("You don't have permission for this action."))

    if scheduled_messages.cancel_message(message):
        messages.success(request, _("Scheduled message cancelled."))
    else:
        messages.warning(request, _("This message was already sent or cancelled."))
    if target is not None:
        return redirect(_target_url(target))
    return redirect("notification:settings")


def _read_preference_values(post, prefix=""):
    return {f: post.get(prefix + f) == "on" for f in preferences.PREFERENCE_FIELDS}


def preference_rows(pref):
    """[(group_key, group_label, [(field, label, value), ...]), ...] for templates."""
    labels = {
        "requests": _("Requests"),
        "reminders": _("Reminders"),
        "messages": _("Messages"),
    }
    rows = []
    for key, fields in preferences.PREFERENCE_GROUPS:
        items = [
            (f, pref._meta.get_field(f).verbose_name, getattr(pref, f))
            for f in fields
        ]
        rows.append((key, labels[key], items))
    return rows


@staff_member_required
def settings_page(request):
    """Own notification settings — any staff user, no extra permission."""
    if request.method == "POST":
        preferences.update_preferences(request.user, _read_preference_values(request.POST))
        messages.success(request, _("Notification settings saved."))
        return redirect("notification:settings")

    pref = preferences.get_preferences(request.user)
    context = {
        **admin.site.each_context(request),
        "title": _("Notification settings"),
        "groups": preference_rows(pref),
        "my_messages": ScheduledMessage.objects.filter(
            author=request.user, status=MessageStatus.PENDING,
        ).order_by("send_at")[:20],
    }
    return render(request, "notification/settings.html", context)


@require_POST
@staff_member_required
def user_preferences(request, user_id):
    """Save from the admin user page's Notifications tab. The tab sits inside
    the user change form, so the button posts the whole form here via
    formaction; only the notif_-prefixed fields are read."""
    target_user = get_object_or_404(User, pk=user_id)
    if target_user.pk != request.user.pk and not user_has_perm(request.user, "manage_notification_settings"):
        return HttpResponseForbidden(gettext("You don't have permission for this action."))
    if target_user.is_superuser and not request.user.is_superuser:
        return HttpResponseForbidden(gettext("You don't have permission for this action."))

    preferences.update_preferences(target_user, _read_preference_values(request.POST, prefix="notif_"))
    messages.success(request, _("Notification settings saved."))

    return redirect(reverse("admin:auth_user_change", args=[target_user.pk]) + "?tab=notifications")
