from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from crm.zetom.models import DepartmentsVariants

User = get_user_model()


class Permission(models.Model):
    code = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class Role(models.Model):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    permissions = models.ManyToManyField(Permission, blank=True)

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    # tymir — заменил одиночное `department` (CharField) на `departments` (ArrayField)
    # и завёл `main_departments` для отметки primary-отделов (dep_head может быть
    # primary в нескольких). Инвариант `main_departments ⊆ departments` валидируется
    # в clean() (см. ниже).
    main_departments = ArrayField(
        models.CharField(max_length=30, choices=DepartmentsVariants.choices),
        default=list,
        blank=True,
    )
    departments = ArrayField(
        models.CharField(max_length=30, choices=DepartmentsVariants.choices),
        default=list,
        blank=True,
    )
    job_title = models.CharField(max_length=100, null=True, blank=True)
    role = models.ForeignKey(Role, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return f"{self.user.username} - {self.role}"

    def is_role(self, code):
        return self.role and self.role.code == code

    # claude
    def clean(self):
        super().clean()
        invalid = set(self.main_departments or []) - set(self.departments or [])
        if invalid:
            raise ValidationError({
                "main_departments": _(
                    "A department can be marked as main only if the user already "
                    "belongs to it."
                ),
            })

    # claude
    def departments_summary(self, limit=3):
        """Short human-readable list of departments for headers/lists.

        Primary departments come first, then the rest sorted alphabetically by label.
        If there are more than `limit`, append "+N" suffix.
        """
        codes = list(self.departments or [])
        if not codes:
            return ""
        labels = dict(DepartmentsVariants.choices)
        main_set = set(self.main_departments or [])
        ordered = sorted(
            codes,
            key=lambda c: (0 if c in main_set else 1, labels.get(c, c).lower()),
        )
        head = ordered[:limit]
        extra = len(ordered) - limit
        text = ", ".join(labels.get(c, c) for c in head)
        if extra > 0:
            text = f"{text}, +{extra}"
        return text
