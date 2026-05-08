from django.urls import path

from . import views

urlpatterns = [
    path("", views.UserListView.as_view(), name="user_list"),
    path("create/", views.UserCreateView.as_view(), name="user_create"),
    path("<int:pk>/edit/", views.UserEditView.as_view(), name="user_edit"),
    path("<int:pk>/delete/", views.UserDeleteView.as_view(), name="user_delete"),
    path("<int:pk>/", views.UserDetailView.as_view(), name="user_detail"),
    path("me/", views.UserProfileEditView.as_view(), name="user_profile_edit"),
]
