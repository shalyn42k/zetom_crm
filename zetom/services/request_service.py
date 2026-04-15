from django.shortcuts import get_object_or_404

from ..models import Oferta, RequestMain, RequestNull


def approve_null_action(null_id):
    null_obj = get_object_or_404(RequestNull, pk=null_id)

    main_obj, created = RequestMain.objects.update_or_create(
        from_null=null_obj,
        defaults={
            "phone": null_obj.phone,
            "company_name": null_obj.company_name,
            "company_nip": null_obj.company_nip,
            "email": null_obj.email,
        }
    )

    null_obj.delete()

    return main_obj


def approve_oferta_action(main_id):
    main_obj = get_object_or_404(RequestMain, pk=main_id)

    oferta_obj, created = Oferta.objects.update_or_create(
        from_main=main_obj,
        defaults={
            "phone": main_obj.phone,
            "company_name": main_obj.company_name,
            "company_nip": main_obj.company_nip,
            "email": main_obj.email,
        },
    )

    if created:
        oferta_obj.price = 0
        oferta_obj.save()

    return oferta_obj
