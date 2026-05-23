"""Template context for the inapp notifications badge.

Adds `notifications_unread_count` to every template so the sidebar
avatar badge (in our overridden `unfold/helpers/navigation_user.html`)
can show how many unread inapp records the user has.
"""
# Local imports
from crm.notification.utils import unread_count


# claude
def unread_notifications(request):
    return {
        "notifications_unread_count": unread_count(getattr(request, "user", None)),
    }
