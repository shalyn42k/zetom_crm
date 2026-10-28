# claude
"""The request's own copy of client data ("Client information").

When a client is linked, its data and its company's data fill the request's
fields that are still empty — never the ones someone already typed. After
that the copy belongs to the request: editing it never touches the client
base. Oferta / Zlecenie / Wniosek copy it again when they are created
(request_service._approve_child).
"""
SNAPSHOT_FIELDS = ("first_name", "last_name", "company_name", "company_nip", "email", "phone", "address")


def client_values(client):
    """What a client record (and its first company) can offer for the copy."""
    company = client.primary_company() if callable(getattr(client, "primary_company", None)) else None
    values = {
        "first_name": client.first_name or "",
        "last_name": client.last_name or "",
        "email": client.email or "",
        "phone": client.phone or "",
    }
    if company is not None:
        address = ", ".join(p for p in (company.street, " ".join(p for p in (company.post_code, company.city) if p)) if p)
        values.update({
            "company_name": company.name or "",
            "company_nip": company.nip or "",
            "address": address,
        })
    return values


def fill_empty_from_client(request_obj, client):
    """Fill the request's empty snapshot fields from `client`; returns the
    {field: value} that were filled (also saved)."""
    filled = {}
    for field, value in client_values(client).items():
        if not value or not hasattr(request_obj, field):
            continue
        if getattr(request_obj, field) in (None, ""):
            setattr(request_obj, field, value)
            filled[field] = str(value)
    if filled:
        request_obj.save(update_fields=list(filled))
    return filled
