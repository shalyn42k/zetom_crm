# claude
"""Notification settings: the own settings page (any staff user) and the
save endpoint behind the Notifications tab of the admin user page."""
from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext, gettext_lazy as _
from django.views.decorators.http import require_POST

from crm.notification.services import preferences
from crm.users.utils import user_has_perm

User = get_user_model()


def _read_preference_values(post, prefix=""):
    return {f: post.get(prefix + f) == "on" for f in preferences.PREFERENCE_FIELDS}


def preference_rows(pref):
    """[(group_key, group_label, [(field, label, value), ...]), ...] for templates."""
    labels = {
        "requests": _("Requests"),
        "reminders": _("Reminders"),
    }
    rows = []
    for key, fields in preferences.PREFERENCE_GROUPS:
        items = [(f, pref._meta.get_field(f).verbose_name, getattr(pref, f)) for f in fields]
        rows.append((key, labels[key], items))
    return rows


@staff_member_required
def settings_page(request):
    """Own notification settings — any staff user, no extra permission."""
    if request.method == "POST":
        preferences.update_preferences(request.user, _read_preference_values(request.POST))
        messages.success(request, _("Notification settings saved."))
        return redirect("notification:settings")

    context = {
        **admin.site.each_context(request),
        "title": _("Notification settings"),
        "groups": preference_rows(preferences.get_preferences(request.user)),
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
