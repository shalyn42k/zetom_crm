from django.urls import path

from . import views

urlpatterns = [
    path("", views.UserListView.as_view(), name="user_list"),
    path("create/", views.UserCreateView.as_view(), name="user_create"),
    path("<int:pk>/edit/", views.UserEditView.as_view(), name="user_edit"),
    # claude — маршрут раньше жёстко удалял юзера (name="user_delete").
    # Теперь это деактивация; путь оставлен прежним, чтобы не ломать
    # сохранённые ссылки, имя переименовано под фактическое поведение.
    path("<int:pk>/delete/", views.UserDeactivateView.as_view(), name="user_deactivate"),
    path("<int:pk>/", views.UserDetailView.as_view(), name="user_detail"),
    path("me/", views.UserProfileEditView.as_view(), name="user_profile_edit"),
    path("2fa/", views.otp_gate, name="otp_gate"),
    path("2fa/backup-codes/", views.otp_backup_codes, name="otp_backup_codes"),
]
