// claude — search-as-you-type replacement for the old #id_client <select>,
// which rendered the whole client base as <option>s on every request form.
//
// Binds to [data-client-picker]; the hidden input named in data-target holds
// the picked client's pk. See crm/clients/fields.py for the contract the
// Requests redesign has to preserve.
//
// The dropdown is styled inline on purpose: the request form is due a full
// visual redesign, and shipping CSS for it now would only be something to
// undo. Same throwaway approach client_search.js already uses.
document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-client-picker]").forEach(setupPicker);

    function setupPicker(input) {
        const hidden = document.getElementById(input.dataset.target);
        if (!hidden) return;

        const dropdown = document.createElement("div");
        dropdown.className = "client-picker-dropdown";
        dropdown.style.position = "absolute";
        dropdown.style.zIndex = 9999;
        dropdown.style.display = "none";
        dropdown.style.maxHeight = "280px";
        dropdown.style.overflowY = "auto";
        dropdown.style.minWidth = "260px";
        dropdown.style.border = "1px solid var(--border-color, #444)";
        dropdown.style.borderRadius = "6px";
        dropdown.style.background = "var(--body-bg, #1e1e1e)";
        input.parentNode.appendChild(dropdown);

        const setField = (selector, value) => {
            const field = document.querySelector(selector);
            if (field) field.value = value || "";
        };

        const hide = () => { dropdown.style.display = "none"; };

        // claude — one search call carries everything both consumers need:
        // the pk for the Link button and the contact fields for the prefill.
        // The old flow picked an option, then fired a second request to
        // /clients/autofill/ to fetch the very same values.
        const choose = (client) => {
            hidden.value = client.id;
            input.value = client.label;
            setField("#id_first_name", client.first_name);
            setField("#id_last_name", client.last_name);
            setField("#id_company_name", client.company_name);
            setField("#id_company_nip", client.company_nip);
            setField("#id_email", client.email);
            setField("#id_phone", client.phone);
            setField("#id_address", client.address);
            hide();
        };

        let timer = null;

        input.addEventListener("input", function () {
            // typing after a pick invalidates it — never leave a stale pk
            // behind the box while the text says something else
            hidden.value = "";
            const q = input.value.trim();
            if (!q) { hide(); return; }

            clearTimeout(timer);
            timer = setTimeout(() => {
                fetch(`/clients/search/?q=${encodeURIComponent(q)}`)
                    .then((r) => r.json())
                    .then((data) => {
                        dropdown.innerHTML = "";
                        if (!data.results || !data.results.length) { hide(); return; }

                        data.results.forEach((client) => {
                            const item = document.createElement("div");
                            item.style.padding = "6px 10px";
                            item.style.cursor = "pointer";
                            item.style.borderBottom = "1px solid var(--border-color, #333)";
                            item.innerText = client.company_nip
                                ? `${client.label} (${client.company_nip})`
                                : client.label;
                            item.addEventListener("click", () => choose(client));
                            dropdown.appendChild(item);
                        });
                        dropdown.style.display = "block";
                    })
                    .catch(hide);
            }, 300);
        });

        document.addEventListener("click", function (e) {
            if (!dropdown.contains(e.target) && e.target !== input) hide();
        });
    }
});
