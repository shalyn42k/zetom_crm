"""URLs for the inapp notifications inbox."""
# Django imports
from django.urls import path

# Local imports
from crm.notification import views

app_name = "notification"

urlpatterns = [
    path("", views.inbox, name="inbox"),
    path("<int:pk>/read/", views.mark_read, name="mark_read"),
    path("read-all/", views.mark_all_read, name="mark_all_read"),
]
