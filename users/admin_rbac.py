from django.contrib import admin

class RBACAdmin(admin.ModelAdmin):
   
    def _get_profile(self, request):
        user = request.user
        if not user.is_authenticated:
            return None
        return getattr(user, "userprofile", None)

    def has_view_permission(self, request, obj=None):
        profile = self._get_profile(request)
        if not profile:
            return False

        model_name = self.model.__name__.lower()

        # скрыть модель
        if profile.is_model_hidden(model_name):
            return False

        # просмотр разрешён
        return True

    def has_change_permission(self, request, obj=None):
        profile = self._get_profile(request)
        if not profile:
            return False

        model_name = self.model.__name__.lower()

        # если модель readonly запрещаем редактирование
        if profile.is_model_readonly(model_name):
            return False

        # если модель не в списке редактируемых запрещаем
        if not profile.can_edit_model(model_name):
            return False

        return True

    def has_add_permission(self, request):
        return self.has_change_permission(request)

    def has_delete_permission(self, request, obj=None):
        return self.has_change_permission(request)
