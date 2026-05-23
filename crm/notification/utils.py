"""Тонкие хелперы для шапки Unfold и context-processor'ов."""


# claude
def unread_count(user):
    """Quick lookup for "how many unread inapp notifications does this user have".

    Backed by the (recipient, is_read) index on `Notification.Meta` — should
    be a constant-time hit even on a large table.
    """
    if not user or not user.is_authenticated:
        return 0
    return user.inapp_notifications.filter(is_read=False).count()
