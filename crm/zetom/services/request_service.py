# Django imports
from django.shortcuts import get_object_or_404

from crm.status_manager.services.status_service import update_parent
# Zetom app imports
from crm.zetom.models import (Oferta, RequestMain, RequestNull, RequestSource,
                              Wniosek, Zlecenie)
from crm.zetom.services.status_orchestration import (
    close_oferta_on_zlecenie, close_zlecenie_on_wniosek,
)


def approve_null_action(null_id):
    null_obj = get_object_or_404(RequestNull, pk=null_id)

    main_obj, created = RequestMain.objects.update_or_create(
        from_null=null_obj,
        defaults={
            "first_name": null_obj.first_name,
            "last_name": null_obj.last_name,
            "phone": null_obj.phone,
            "company_name": null_obj.company_name,
            "company_nip": null_obj.company_nip,
            "email": null_obj.email,
            "message": null_obj.message,
            "departments": [],
            "source": null_obj.source,
        },
    )

    null_obj.delete()

    return main_obj


def _approve_child(model, main_id, **extra):
    main_obj = get_object_or_404(RequestMain, pk=main_id)
    child = model.objects.create(
        from_main=main_obj,
        phone=main_obj.phone,
        company_name=main_obj.company_name,
        company_nip=main_obj.company_nip,
        email=main_obj.email,
        source=RequestSource.PARENT,
        **extra,
    )
    
    child.assigned_to.set(main_obj.assigned_to.all())

    update_parent(main_obj)
    return child


def approve_oferta_action(main_id):
    return _approve_child(Oferta, main_id, price=0)


# claude — Fix-round: reinstated after a Fix-round that stripped this too
# far — the user only asked to remove the per-document "create next" chain
# buttons living ON Oferta/Zlecenie's own change forms (children.py), not
# this RequestMain-page path. Opening a zlecenie closes every not-yet-done
# oferta on this request, same rule as before.
def approve_zlecenie_action(main_id, user=None):
    zlecenie = _approve_child(Zlecenie, main_id, price=0)
    for oferta in zlecenie.from_main.oferta_set.all():
        close_oferta_on_zlecenie(oferta, user)
    return zlecenie


def approve_wniosek_action(main_id, user=None):
    wniosek = _approve_child(Wniosek, main_id)
    for zlecenie in wniosek.from_main.zlecenie_set.all():
        close_zlecenie_on_wniosek(zlecenie, user)
    return wniosek
