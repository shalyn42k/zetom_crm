// claude — what remains here is the NIP-on-blur autofill: type a NIP into the
// request form and the matching firm's contact details fill themselves in.
//
// The other half of this file used to listen for `change` on the #id_client
// <select> and then re-fetch, by NIP parsed out of the option's own text, the
// data that select already had. That select is now a hidden input plus a search
// box (crm/clients/fields.py), which fires no `change` and has no option text —
// and client_picker.js fills the same fields straight from the search result it
// already holds, without the second round trip.
document.addEventListener("DOMContentLoaded", function () {
    const nipField = document.getElementById("id_company_nip");
    if (!nipField) return;

    const mapping = {
        "id_phone": "phone",
        "id_email": "email",
        "id_company_name": "company_name",
        "id_company_nip": "company_nip",
        "id_address": "address",
        "id_first_name": "first_name",
        "id_last_name": "last_name",
    };

    const fillFields = (data) => {
        Object.entries(mapping).forEach(([id, key]) => {
            const field = document.getElementById(id);
            const value = data[key];
            if (field && value) field.value = value;
        });
    };

    nipField.addEventListener("blur", function () {
        const nip = this.value.trim();
        if (!nip) return;

        fetch(`/clients/autofill/?nip=${encodeURIComponent(nip)}`)
            .then((r) => {
                if (!r.ok) throw new Error("no_client");
                return r.json();
            })
            .then((data) => {
                if (!data.exists) return;
                fillFields(data);
            })
            .catch(() => {
                // no matching client, ignore
            });
    });
});
