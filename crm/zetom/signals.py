from django.db.models.signals import post_delete # сигнал который срабатывает после удаления 
from crm.zetom.services.services import update_parent 
from crm.zetom.models import Oferta, Zlecenie, Wniosek 
from django.dispatch import receiver # вызов функции с сигналом 

@receiver(post_delete, sender=Oferta)
def oferta_deleted(sender, instance, **kwargs):  
    if instance.from_main:   # instance это обьект который удалили 
        update_parent(instance.from_main)


@receiver(post_delete, sender=Zlecenie)
def zlecenie_deleted(sender, instance, **kwargs):
    if instance.from_main:
        update_parent(instance.from_main)


@receiver(post_delete, sender=Wniosek)
def wniosek_deleted(sender, instance, **kwargs):
    if instance.from_main:
        update_parent(instance.from_main)