"""Тонкие хелперы для шапки Unfold, context-processor'ов и inbox-страницы."""
# Django imports
from django.template.loader import render_to_string


# claude
def unread_count(user):
    """Quick lookup for "how many unread inapp notifications does this user have".

    Backed by the (recipient, is_read) index on `Notification.Meta` — should
    be a constant-time hit even on a large table.
    """
    if not user or not user.is_authenticated:
        return 0
    return user.inapp_notifications.filter(is_read=False).count()


# claude
def split_subject_body(rendered):
    """First non-empty line is the title, the rest is the body.

    Leading whitespace (typical leftover from a `{% comment %}` block at the
    top of an inapp template) is stripped before splitting.
    """
    stripped = rendered.lstrip()
    if "\n" in stripped:
        title, body = stripped.split("\n", 1)
    else:
        title, body = stripped, ""
    return title.strip(), body.lstrip("\n").rstrip()


# claude
def render_notification(notification):
    """Render the inapp notification's template lazily; return (title, body) tuple.

    Falls back to ("(template missing)", "") if the template file is gone —
    so old DB rows pointing at a deleted template don't crash the inbox.
    """
    try:
        rendered = render_to_string(notification.template_name, notification.payload or {})
    except Exception:
        return ("(template missing)", "")
    return split_subject_body(rendered)


# claude
def target_url(notification):
    """Best-effort URL for the GFK target. None if target is gone or unsupported."""
    if not (notification.target_content_type_id and notification.target_object_id):
        return None
    target = notification.target
    if target is None:
        return None
    # Prefer model-defined get_absolute_url(); otherwise route via Django admin
    # change_view of the model.
    if hasattr(target, "get_absolute_url"):
        try:
            return target.get_absolute_url()
        except Exception:
            pass
    from django.urls import NoReverseMatch, reverse
    ct = notification.target_content_type
    try:
        return reverse(
            f"admin:{ct.app_label}_{ct.model}_change",
            args=[notification.target_object_id],
        )
    except NoReverseMatch:
        return None
