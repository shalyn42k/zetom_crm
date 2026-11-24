from django.dispatch import receiver  # вызов функции с сигналом
from safedelete.signals import \
    post_softdelete  # сигнал который срабатывает после удаления

from crm.status_manager.services.status_service import update_parent
from crm.zetom.models import Oferta, Wniosek, Zlecenie


@receiver(post_softdelete, sender=Oferta)
def oferta_deleted(sender, instance, **kwargs):  
    if instance.from_main:   # instance это обьект который удалили 
        update_parent(instance.from_main)


@receiver(post_softdelete, sender=Zlecenie)
def zlecenie_deleted(sender, instance, **kwargs):
    if instance.from_main:
        update_parent(instance.from_main)


@receiver(post_softdelete, sender=Wniosek)
def wniosek_deleted(sender, instance, **kwargs):
    if instance.from_main:
        update_parent(instance.from_main)

