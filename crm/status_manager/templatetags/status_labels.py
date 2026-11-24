"""Template filter to turn a raw RequestStatus/Status code into its
translated label, resolved at render time (not baked in when a Notification
payload is written) — so a notification shows the viewer's own active
language, not whatever was active at the moment it was created.
"""
from django import template

from crm.status_manager.services.statuses import RequestStatus, Status

register = template.Library()


@register.filter
def request_status_label(code):
    """RequestStatus code -> translated label; falls back to the raw code
    for anything that isn't a known value (e.g. a notification payload from
    before this field existed, or a stale/unexpected value)."""
    try:
        return RequestStatus(code).label
    except ValueError:
        return code


@register.filter
def doc_status_label(code):
    """Same as request_status_label, for the child-document Status enum."""
    try:
        return Status(code).label
    except ValueError:
        return code
