document.addEventListener("DOMContentLoaded", function () {
    const clientSelect = document.getElementById("id_client");
    const nipField = document.getElementById("id_company_nip");

    const mapping = {
        "id_phone": "phone",
        "id_email": "email",
        "id_company_name": "company_name",
        "id_company_nip": "nip",
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
Т
    if (clientSelect) {
        clientSelect.addEventListener("change", function () {
            const selectedOption = this.options[this.selectedIndex];
            const query = selectedOption.text || "";
            if (!query) return;

            const nipMatch = query.match(/\(([^)]+)\)\s*$/);
            if (nipMatch) {
                const nip = nipMatch[1].trim();
                if (nip) {
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
                            // fallback to search if autofill by nip failed
                        });
                    return;
                }
            }

            fetch(`/clients/search/?q=${encodeURIComponent(query)}`)
                .then((r) => r.json())
                .then((data) => {
                    if (!data.results.length) return;
                    fillFields(data.results[0]);
                });
        });
    }

    if (nipField) {
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
    }
});
