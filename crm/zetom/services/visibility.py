from django.db.models import Q


def visible_requests_for(user, qs):
    """
    Возвращает qs, отфильтрованный под права текущего юзера.

    qs — любой queryset модели, унаследованной от RequestTemplate
    (RequestNull, RequestMain, Oferta, Zlecenie, Wniosek).

    Правила:
      - суперюзер / админ → всё;
      - спец → только то, где он в assigned_to ИЛИ assigned_to пустой;
      - нет профиля или роли → ничего (защитный случай).
    """
    if user.is_superuser:
        return qs

    profile = getattr(user, "profile", None)
    if not profile or not profile.role:
        return qs.none()

    if profile.is_role("specialist"):
        personal = Q(assigned_to=user)

        if profile.department:
            pool = Q(assigned_to__isnull=True) & Q(department=profile.department)
            return qs.filter(personal | pool).distinct()

        return qs.filter(personal).distinct()

    # admin, department_head, auditor, all_seeing — на демо видят всё
    return qs
