# Django imports
from django.shortcuts import get_object_or_404

# Zetom app imports
from crm.zetom.models import (Oferta, RequestMain, RequestNull, Wniosek,
                              Zlecenie)
from crm.zetom.services.services import update_parent


def approve_null_action(null_id):
    null_obj = get_object_or_404(RequestNull, pk=null_id)

    main_obj, created = RequestMain.objects.update_or_create(
        from_null=null_obj,
        defaults={
            "phone": null_obj.phone,
            "company_name": null_obj.company_name,
            "company_nip": null_obj.company_nip,
            "email": null_obj.email,
            "message": null_obj.message,
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
        **extra,
    )
    update_parent(main_obj)
    return child


def approve_oferta_action(main_id):
    return _approve_child(Oferta, main_id, price=0)


def approve_zlecenie_action(main_id):
    return _approve_child(Zlecenie, main_id, price=0)


def approve_wniosek_action(main_id):
    return _approve_child(Wniosek, main_id)
