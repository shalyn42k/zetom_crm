from django.db import models


class Status(models.TextChoices):
    new = "new", "New"
    in_progress = "in_progress", "In Progress"
    waiting = "waiting", "Waiting"
    done = "done", "Done"


class RequestStatus(models.TextChoices):
    active = "active"
    open = "open"
    closed = "closed"
    inactive = "inactive"
    cancelled = "cancelled"
    deleted = "deleted"
