# claude
"""Reads NotificationPreference and filters recipient lists by it.

The send pipeline calls `filter_inapp` / `filter_email` right before it
creates rows or sends mail, so muting a kind is respected everywhere
without each trigger knowing about preferences. Kinds that are missing
from the maps below (review request/resolve, system) can't be muted.
"""
from crm.notification.models import NotificationKind, NotificationPreference

INAPP_FIELD_BY_KIND = {
    NotificationKind.ASSIGNMENT: "inapp_assignment",
    NotificationKind.STATUS_CHANGE: "inapp_status_change",
    NotificationKind.REMINDER: "inapp_reminders",
}

EMAIL_FIELD_BY_KIND = {
    NotificationKind.REMINDER: "email_reminders",
}

# Order and grouping of the switches on the user's Notifications tab.
PREFERENCE_GROUPS = (
    ("requests", ("inapp_assignment", "inapp_status_change")),
    ("reminders", ("inapp_reminders", "email_reminders")),
)
PREFERENCE_FIELDS = tuple(f for _group, fields in PREFERENCE_GROUPS for f in fields)


def get_preferences(user):
    """Saved row for `user`, or an unsaved one carrying the defaults."""
    pref = NotificationPreference.objects.filter(user=user).first()
    return pref or NotificationPreference(user=user)


def update_preferences(user, values):
    """Persist the switches in `values` (field name -> bool)."""
    pref, _created = NotificationPreference.objects.get_or_create(user=user)
    for field in PREFERENCE_FIELDS:
        setattr(pref, field, bool(values.get(field, False)))
    pref.save()
    return pref


def _filter(recipients, field):
    recipients = list(recipients)
    if field is None or not recipients:
        return recipients
    default = NotificationPreference._meta.get_field(field).default
    saved = dict(
        NotificationPreference.objects.filter(
            user__in=[u.pk for u in recipients]
        ).values_list("user_id", field)
    )
    return [u for u in recipients if saved.get(u.pk, default)]


def filter_inapp(recipients, kind):
    return _filter(recipients, INAPP_FIELD_BY_KIND.get(kind))


def filter_email(recipients, kind):
    """Users who accept email for `kind` and actually have an address."""
    field = EMAIL_FIELD_BY_KIND.get(kind)
    if field is None:
        return [u for u in recipients if u.email]
    return [u for u in _filter(recipients, field) if u.email]
