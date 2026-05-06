from django.db import models


class Status(models.TextChoices):
    new = "new", "New"
    in_progress = "in_progress", "In Progress"
    waiting = "waiting", "Waiting"
    done = "done", "Done"


class RequestStatus(models.TextChoices):
    active = "active", "Active"
    open = "open", "Open"
    closed = "closed", "Closed"
    inactive = "inactive", "Inactive"
    cancelled = "cancelled", "Cancelled"
    deleted = "deleted", "Deleted"
