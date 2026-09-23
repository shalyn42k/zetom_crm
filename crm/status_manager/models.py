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


class ChildDocumentDeletion(models.Model):
    """Audit log for deleting an Oferta/Zlecenie/Wniosek.

    Child documents are hard-deleted (no soft-delete/status=deleted, unlike
    RequestMain), so this is the only record left once the row is gone —
    hence document_repr/document_type snapshots instead of a live FK to the
    deleted object.
    """
    document_type = models.CharField(max_length=20)
    document_repr = models.CharField(max_length=255)
    from_main = models.ForeignKey(
        "zetom.RequestMain",
        on_delete=models.SET_NULL,
        null=True,
        related_name="child_document_deletions",
    )
    reason = models.TextField(blank=True)
    deleted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    deleted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.document_type} {self.document_repr}"

    class Meta:
        ordering = ["-deleted_at"]
