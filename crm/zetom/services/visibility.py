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

        # claude — было: одиночное profile.department + departments__contains=[code].
        # Теперь юзер может состоять в N отделах → пересечение через __overlap.
        if profile.departments:
            same_dept = Q(departments__overlap=profile.departments)
            return qs.filter(personal | same_dept).distinct()

        return qs.filter(personal).distinct()

    # admin, department_head, auditor, all_seeing — на демо видят всё
    return qs
