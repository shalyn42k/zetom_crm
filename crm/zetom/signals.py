# claude — keeps per-instance caches on RequestMain honest when the owners
# list changes on the same object within one request (see
# crm/zetom/services/per_req_perms.is_owner_of_req).
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from crm.zetom.models import Department, RequestMain, reset_department_cache


@receiver(m2m_changed, sender=RequestMain.owners.through)
def _reset_owner_cache(sender, instance, **kwargs):
    if isinstance(instance, RequestMain):
        instance.__dict__.pop("_owner_ids_cache", None)


@receiver(post_save, sender=Department)
@receiver(post_delete, sender=Department)
def _reset_department_cache(sender, **kwargs):
    reset_department_cache()
