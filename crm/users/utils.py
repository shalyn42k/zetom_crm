# claude — роли, которые non-superuser НЕ может присвоить никому: дают
# глобальные права уровня админа, поэтому только сам superuser вправе
# повышать до них (защита от RBAC-эскалации).
# Живёт здесь, а не в admin/user.py, чтобы `crm.users.views` мог
# импортировать константу, не втягивая за собой весь модуль админки.
PRIVILEGED_ROLE_CODES = frozenset({"admin", "all_seeing"})


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
