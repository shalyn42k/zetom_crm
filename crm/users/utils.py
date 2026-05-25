# claude — проверяем через effective_permissions (role.permissions ∪
# profile.extra_permissions), чтобы индивидуальные права тоже учитывались.
def user_has_perm(user, perm):
    if not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    profile = getattr(user, "profile", None)
    if not profile:
        return False

    return profile.effective_permissions().filter(code=perm).exists()
