def user_has_perm(user, perm):
    if not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    profile = getattr(user, "profile", None)
    if not profile or not profile.role:
        return False

    return profile.role.permissions.filter(code=perm).exists()
