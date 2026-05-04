from django.contrib.auth.models import User
from django.db import models

from crm.status_manager.services.statuses import RequestStatus


class StatusHistory(models.Model):
    request = models.ForeignKey(
        "zetom.RequestMain",
        on_delete=models.CASCADE,
        related_name="status_history",
    )
    old_status = models.CharField(max_length=20, choices=RequestStatus.choices)
    new_status = models.CharField(max_length=20, choices=RequestStatus.choices)
    reason = models.TextField(blank=True)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.request} - {self.new_status}"

    class Meta:
        ordering = ["-changed_at"]
