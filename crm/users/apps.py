print("APPS.PY LOADED")

from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "crm.users"
    label = "users"
    verbose_name = "users"

    def ready(self):
        print("READY() WORKS")
        import crm.users.signals
        import crm.users.signals_profile
        _install_avatar_url()


# claude — Unfold уже везде рисует аватар через {{ user.avatar_url }}
# (sidebar navigation_user.html и т.п.), просто у auth.User такого поля
# нет. Добавляем его как property через add_to_class вместо своей копии
# чужих шаблонов — тогда работает автоматически везде, где Unfold уже
# рисует аватарки, без единой правки на их стороне.
def _install_avatar_url():
    from django.contrib.auth.models import User

    def avatar_url(self):
        profile = getattr(self, "profile", None)
        if profile and profile.avatar:
            return profile.avatar.url
        return _default_avatar_url()

    User.add_to_class("avatar_url", property(avatar_url))


def _default_avatar_url():
    # claude — заглушка, пока на месте нет своей картинки: static() не
    # проверяет существование файла, а finders.find() бьёт по диску при
    # каждом вызове — кэшируем один раз результат первой проверки.
    from django.contrib.staticfiles import finders
    from django.templatetags.static import static

    if _default_avatar_url.cache is None:
        _default_avatar_url.cache = static("img/default_avatar.jpg") if finders.find("img/default_avatar.jpg") else ""
    return _default_avatar_url.cache


_default_avatar_url.cache = None
