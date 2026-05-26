"""Per-Req permission model.

owners это per-Req флаг (M2M `RequestMain.owners`), который даёт
дополнительные права поверх роли — но только на конкретном Req'е.

Иерархия на одном Req:
    admin > dep_head_of_Req_departments > owner > specialist

Помощники здесь возвращают bool и собраны в одном месте, чтобы не
расползались дублирующиеся проверки по admin/template коду. Логика и
обоснование — в memory/project_per_req_permissions.md.
"""
# Django imports
from django.contrib.auth import get_user_model

# Local imports
from crm.users.utils import user_has_perm

# claude
User = get_user_model()

ROLE_ADMIN = "admin"
ROLE_DEP_HEAD = "department_head"
ROLE_SPECIALIST = "specialist"


# claude
def _role_code(user):
    """Return role.code or None for active users."""
    if not getattr(user, "is_authenticated", False):
        return None
    profile = getattr(user, "profile", None)
    role = getattr(profile, "role", None) if profile else None
    return getattr(role, "code", None)


# claude
def is_admin(user):
    """admin = role.code == 'admin' OR is_superuser."""
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return _role_code(user) == ROLE_ADMIN


# claude
def is_dep_head_of_req(user, req):
    """User counts as dep_head for this Req only when they head one of
    the Req's departments. dep_head чужого отдела на этом Req — обычный юзер.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if _role_code(user) != ROLE_DEP_HEAD:
        return False
    profile = getattr(user, "profile", None)
    head = set(getattr(profile, "head_of_departments", None) or [])
    return bool(head & set(req.departments or []))


# claude
def is_owner_of_req(user, req):
    if not getattr(user, "is_authenticated", False):
        return False
    return req.owners.filter(pk=user.pk).exists()


# claude
def can_manage_owners(user, req):
    """Right to set/unset the owner flag on this Req.

    Контекстно: admin / dep_head_of_Req. Плюс — глобальный permission
    `manage_owners` (выдаётся через role или extra_permissions), чтобы
    админ мог делегировать управление owners например auditor'у или
    отдельному «PM» без выдачи полной роли dep_head.
    """
    if is_admin(user) or is_dep_head_of_req(user, req):
        return True
    return user_has_perm(user, "manage_owners")


# claude
def can_assign_anyone(user, req):
    """admin / dep_head_of_Req can add/remove ANY user to/from assigned_to."""
    return is_admin(user) or is_dep_head_of_req(user, req)


# claude
def can_assign_target(user, target, req):
    """Right to ADD `target` to `req.assigned_to`.

    Matrix:
      - admin / dep_head_of_Req → any active target.
      - owner_of_Req → only specialists (any role with code 'specialist').
      - non-owner specialist → no rights.
    """
    if not target.is_active:
        return False
    if can_assign_anyone(user, req):
        return True
    if is_owner_of_req(user, req):
        return _role_code(target) == ROLE_SPECIALIST
    return False


# claude
def can_unassign_target(user, target, req):
    """Mirror of `can_assign_target` for unassign. Owners may unassign
    other specialists (including specialist-owners). Removing an assigned
    user also clears their owner flag (handled by the action)."""
    if can_assign_anyone(user, req):
        return True
    if is_owner_of_req(user, req):
        return _role_code(target) == ROLE_SPECIALIST
    return False


# claude
def can_resolve_review(user, req):
    """`resolve_review` role permission OR owner_of_Req."""
    if user_has_perm(user, "resolve_review"):
        return True
    return is_owner_of_req(user, req)


# claude
def request_review_eligible(sender, target, req):
    """Can `sender` request review FROM `target` on this `req`?

    Sender → eligible targets (per per-Req hierarchy):
      specialist → owners(any role) + dep_heads(any) + admins
      dep_head   → admins only
      admin      → anyone in the same pool (owners + dep_heads + admins)

    Always excludes self and inactive users.
    """
    if not target.is_active or target.pk == sender.pk:
        return False

    target_role = _role_code(target)
    target_is_owner = is_owner_of_req(target, req)
    target_is_admin = is_admin(target)
    target_is_dep_head = target_role == ROLE_DEP_HEAD

    if is_admin(sender):
        return target_is_owner or target_is_dep_head or target_is_admin
    if _role_code(sender) == ROLE_DEP_HEAD:
        return target_is_admin
    # specialist (and anything else) — escalates up
    return target_is_owner or target_is_dep_head or target_is_admin
