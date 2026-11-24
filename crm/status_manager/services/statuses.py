from django.db import models
from django.utils.translation import gettext_lazy as _


class Status(models.TextChoices):
    new = "new", _("New")
    in_progress = "in_progress", _("In Progress")
    waiting = "waiting", _("Waiting")
    done = "done", _("Done")


class RequestStatus(models.TextChoices):
    active = "active", _("Active")
    open = "open", _("Open")
    closed = "closed", _("Closed")
    inactive = "inactive", _("Inactive")
    cancelled = "cancelled", _("Cancelled")
    deleted = "deleted", _("Deleted")
