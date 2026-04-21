from django.db import models


class Status(models.TextChoices):
    new = "new"
    in_progress = "in_progress"
    waiting = "waiting"
    done = "done"



class ArchiveState:
    active = 'active'
    archive = 'archive'
