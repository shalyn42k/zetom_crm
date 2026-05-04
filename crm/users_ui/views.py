from django.views import View
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User
from django.contrib import messages

from .forms import (
    CustomUserCreateForm,
    CustomUserChangeForm,
    UserProfileEditForm,
)
from crm.users.models import UserProfile


class UserListView(View):
    """Список всех пользователей"""
    def get(self, request):
        users = User.objects.all().select_related("userprofile")
        return render(request, "users/user_list.html", {"users": users})


class UserCreateView(View):
    """Создание нового пользователя"""
    def get(self, request):
        form = CustomUserCreateForm()
        return render(request, "users/user_form.html", {"form": form, "mode": "create"})

    def post(self, request):
        form = CustomUserCreateForm(request.POST)

        if form.is_valid():
            form.save()
            messages.success(request, "Пользователь успешно создан.")
            return redirect("user_list")

        return render(request, "users/user_form.html", {"form": form, "mode": "create"})


class UserEditView(View):
    """Редактирование пользователя"""
    def get(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        profile = UserProfile.objects.get(user=user)

        form = CustomUserChangeForm(
            instance=user,
            initial={"role": profile.role, "department": profile.department}
        )

        return render(request, "users/user_form.html", {"form": form, "mode": "edit"})

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        profile = UserProfile.objects.get(user=user)

        form = CustomUserChangeForm(
            request.POST,
            instance=user,
            initial={"role": profile.role}
        )

        if form.is_valid():
            form.save()
            messages.success(request, "Пользователь обновлён.")
            return redirect("user_list")

        return render(request, "users/user_form.html", {"form": form, "mode": "edit"})


class UserDeleteView(View):
    """Удаление пользователя"""
    def get(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        return render(request, "users/user_confirm_delete.html", {"user": user})

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        user.delete()
        messages.success(request, "Пользователь удалён.")
        return redirect("user_list")


class UserDetailView(View):
    """Просмотр профиля пользователя"""
    def get(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        profile = UserProfile.objects.get(user=user)
        return render(request, "users/user_detail.html", {"user": user, "profile": profile})


class UserProfileEditView(View):
    """Редактирование своего профиля"""
    def get(self, request):
        form = UserProfileEditForm(instance=request.user)
        return render(request, "users/user_profile_edit.html", {"form": form})

    def post(self, request):
        form = UserProfileEditForm(request.POST, instance=request.user)

        if form.is_valid():
            form.save()
            messages.success(request, "Профиль обновлён.")
            return redirect("user_profile_edit")

        return render(request, "users/user_profile_edit.html", {"form": form})
