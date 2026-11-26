"""Optimistic locking for the request card and the document windows.

claude — two people editing the same request: whoever pressed "Save" last
silently overwrote the other's changes (the admin form writes every field
it carries, including the ones this user never touched). Now the page
carries the `updated_at` it was rendered with; on save the row is locked
(`select_for_update`, the admin change view already runs in a transaction)
and if someone saved in between, the form is refused with a message naming
who changed what. The re-rendered page carries the fresh token, so pressing
Save again is a deliberate overwrite after seeing the warning.

Saves without a token (scripts, tests, older open tabs) are let through
as before.
"""
from datetime import datetime

from django import forms
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext as _

from crm.zetom.services.history_labels import history_field_label

TOKEN_FIELD = "_concurrency_token"


def concurrency_token(obj):
    return obj.updated_at.isoformat() if getattr(obj, "updated_at", None) else ""


def _changes_since(obj, since_token):
    """(who, [field labels]) from simple-history, if the model keeps it."""
    history = getattr(obj, "history", None)
    if history is None:
        return None, []
    try:
        since = datetime.fromisoformat(since_token)
    except ValueError:
        return None, []
    # By the copied updated_at, not history_date: the record of the save
    # that produced the token itself is stamped a moment after it.
    records = list(
        history.filter(updated_at__gt=since)
        .select_related("history_user").order_by("history_date")
    )
    who, fields = None, []
    for record in records:
        who = record.history_user or who
        prev = record.prev_record
        if prev is None:
            continue
        for change in record.diff_against(prev).changes:
            label = str(history_field_label(change.field))
            if label not in fields:
                fields.append(label)
    return who, fields


def conflict_message(obj, since_token, current_updated_at):
    who, fields = _changes_since(obj, since_token)
    when = date_format(timezone.localtime(current_updated_at), "DATETIME_FORMAT")
    name = (who.get_full_name() or who.get_username()) if who else _("another user")
    msg = _(
        "%(who)s saved this record at %(when)s, after you opened it. "
        "Your changes were not saved."
    ) % {"who": name, "when": when}
    if fields:
        msg += " " + _("Changed meanwhile: %(fields)s.") % {"fields": ", ".join(fields)}
    msg += " " + _(
        "Reload the page to see the current data, or press Save again to overwrite it."
    )
    return msg


class OptimisticLockMixin:
    """ModelAdmin mixin; the change template renders
    admin/zetom/shared/_concurrency_token.html inside (or form= to) the form."""

    def get_form(self, request, obj=None, change=False, **kwargs):
        form_class = super().get_form(request, obj, change=change, **kwargs)
        if obj is None:
            return form_class
        model = self.model

        class OptimisticLockForm(form_class):
            def clean(self):
                cleaned = super().clean()
                token = (self.data.get(TOKEN_FIELD) or "").strip()
                if token and self.instance.pk:
                    current = (
                        model._base_manager.select_for_update()
                        .filter(pk=self.instance.pk)
                        .values_list("updated_at", flat=True)
                        .first()
                    )
                    if current is not None and current.isoformat() != token:
                        raise forms.ValidationError(
                            conflict_message(self.instance, token, current),
                            code="stale",
                        )
                return cleaned

        OptimisticLockForm.__name__ = form_class.__name__
        return OptimisticLockForm

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        context["concurrency_token"] = concurrency_token(obj) if obj is not None else ""
        return super().render_change_form(
            request, context, add=add, change=change, form_url=form_url, obj=obj,
        )
