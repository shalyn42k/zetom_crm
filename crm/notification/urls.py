"""URLs for the inapp notifications inbox."""
# Django imports
from django.urls import path

# Local imports
from crm.notification import views, views_messages

app_name = "notification"

urlpatterns = [
    path("", views.inbox, name="inbox"),
    path("unread-count/", views.unread_count_json, name="unread_count"),
    path("<int:pk>/read/", views.mark_read, name="mark_read"),
    path("read-all/", views.mark_all_read, name="mark_all_read"),
    # claude — composer on the document window + notification settings.
    path("messages/send/", views_messages.compose, name="message_compose"),
    path("messages/<int:pk>/cancel/", views_messages.cancel, name="message_cancel"),
    path("settings/", views_messages.settings_page, name="settings"),
    path("settings/user/<int:user_id>/", views_messages.user_preferences, name="user_preferences"),
]
