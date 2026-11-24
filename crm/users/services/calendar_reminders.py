from django.db.models import Exists, OuterRef, Q

from crm.zetom.models import RequestMain, StepNote
from crm.zetom.services.visibility import visible_requests_for


def _default_recipient_targets(queryset, user, author_fallback=False):
    model = queryset.model
    parent_field = "pk" if model is RequestMain else "from_main_id"
    owners = RequestMain.owners.through.objects.filter(
        requestmain_id=OuterRef(parent_field), user__is_active=True,
    )
    target_assignees = model.assigned_to.through.objects.filter(
        **{f"{model._meta.model_name}_id": OuterRef("pk")},
        user__is_active=True,
    )
    main_assignees = RequestMain.assigned_to.through.objects.filter(
        requestmain_id=OuterRef(parent_field), user__is_active=True,
    )
    queryset = queryset.annotate(
        has_owners=Exists(owners),
        is_owner=Exists(owners.filter(user_id=user.pk)),
        has_target_assignees=Exists(target_assignees),
        is_target_assignee=Exists(target_assignees.filter(user_id=user.pk)),
        has_main_assignees=Exists(main_assignees),
        is_main_assignee=Exists(main_assignees.filter(user_id=user.pk)),
    )
    if author_fallback:
        return queryset.filter(
            has_owners=False, has_target_assignees=False, has_main_assignees=False,
        )
    return queryset.filter(
        Q(is_owner=True)
        | Q(has_owners=False, is_target_assignee=True)
        | Q(has_owners=False, has_target_assignees=False, is_main_assignee=True)
    )


def reminders_for_calendar(user, first, last, visible, models, types):
    """Filter reminders using the notification recipient cascade and visibility."""
    if not user.is_active:
        return StepNote.objects.none()

    profile = getattr(user, "profile", None)
    role_codes = [profile.role.code] if profile and profile.role else []
    if user.is_superuser and "admin" not in role_codes:
        role_codes.append("admin")
    explicit = (
        Q(notify__in=(StepNote.Notify.SELF, StepNote.Notify.CLIENT), author=user)
        | Q(notify=StepNote.Notify.USERS, notify_users=user)
    )
    for role in role_codes:
        explicit |= (
            Q(notify=StepNote.Notify.ROLES, notify_roles__contains=[role])
            & ~Q(author=user)
        )

    eligible = Q(pk__in=[])
    fallback = Q(pk__in=[])
    visible_ids = visible.values("pk")
    for model in models:
        targets = visible if model is RequestMain else model.objects.filter(from_main_id__in=visible_ids)
        if model is not RequestMain:
            targets = visible_requests_for(user, targets)
        target_type = Q(target_content_type=types[model])
        eligible |= target_type & Q(
            target_object_id__in=_default_recipient_targets(targets, user).values("pk"),
        )
        fallback |= target_type & Q(
            target_object_id__in=_default_recipient_targets(targets, user, author_fallback=True).values("pk"),
        )
    default = ~Q(notify__in=StepNote.Notify.values) & (
        eligible | (fallback & Q(author=user))
    )
    return StepNote.objects.filter(
        Q(kind=StepNote.Kind.REMINDER, done_at__isnull=True),
        explicit | default,
        next_contact_at__date__range=(first, last),
        target_content_type_id__in=[types[model].pk for model in models],
    ).select_related("target_content_type").distinct()
