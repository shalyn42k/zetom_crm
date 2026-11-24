// claude — search-as-you-type replacement for the old #id_client <select>,
// which rendered the whole client base as <option>s on every request form.
//
// Binds to [data-client-picker]; the hidden input named in data-target holds
// the picked client's pk. See crm/clients/fields.py for the contract the
// Requests redesign has to preserve.
//
document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-client-picker]").forEach(setupPicker);

    // claude — redesign: same list look and keyboard handling as every
    // other searchable dropdown (static/admin/js/combobox.js); styles in
    // static/admin/css/combobox.css. Two-line rows: name, then company ·
    // NIP · email, so people with the same name can be told apart.
    function setupPicker(input) {
        const hidden = document.getElementById(input.dataset.target);
        if (!hidden || input.dataset.cbxReady) return;
        input.dataset.cbxReady = "1";
        const cbx = window.zetomCombobox;
        const emptyText = input.dataset.empty || "—";

        const wrap = document.createElement("div");
        wrap.className = "cbx cbx--search";
        input.parentNode.insertBefore(wrap, input);
        wrap.appendChild(input);
        input.classList.add("cbx__input");
        input.setAttribute("role", "combobox");
        input.setAttribute("aria-expanded", "false");
        const list = document.createElement("ul");
        list.className = "cbx__list";
        list.setAttribute("role", "listbox");
        list.hidden = true;
        wrap.appendChild(list);

        const setField = (selector, value) => {
            const field = document.querySelector(selector);
            if (field) field.value = value || "";
        };
        const hide = () => { list.hidden = true; input.setAttribute("aria-expanded", "false"); };
        let results = [];

        // claude — one search call carries everything both consumers need:
        // the pk for the Link button and the contact fields for the prefill.
        const choose = (client) => {
            if (!client) return;
            hidden.value = client.id;
            input.value = [client.first_name, client.last_name].filter(Boolean).join(" ") || client.label;
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
            hidden.value = "";
            const q = input.value.trim();
            if (!q) { hide(); return; }
            clearTimeout(timer);
            timer = setTimeout(() => {
                fetch(`/clients/search/?q=${encodeURIComponent(q)}`)
                    .then((r) => r.json())
                    .then((data) => {
                        results = data.results || [];
                        // claude — the person first: search labels lead with the
                        // company, so everyone at one firm looked identical.
                        const items = results.map((c) => {
                            const person = [c.first_name, c.last_name].filter(Boolean).join(" ");
                            return {
                                main: person || c.label,
                                sub: [c.company_name, c.company_nip ? "NIP " + c.company_nip : "", c.email]
                                    .filter(Boolean).join(" · "),
                            };
                        });
                        cbx.renderList(list, items, q, emptyText);
                        list.hidden = false;
                        input.setAttribute("aria-expanded", "true");
                    })
                    .catch(hide);
            }, 250);
        });
        input.addEventListener("keydown", function (e) {
            if (list.hidden) return;
            if (e.key === "ArrowDown") { e.preventDefault(); cbx.moveActive(list, 1); }
            else if (e.key === "ArrowUp") { e.preventDefault(); cbx.moveActive(list, -1); }
            else if (e.key === "Enter") { e.preventDefault(); choose(results[cbx.activeIndex(list)]); }
            else if (e.key === "Escape") { hide(); }
        });
        list.addEventListener("mousedown", function (e) {
            const opt = e.target.closest(".cbx__opt");
            if (opt) { e.preventDefault(); choose(results[parseInt(opt.dataset.index, 10)]); }
        });
        input.addEventListener("blur", function () { setTimeout(hide, 120); });
    }
});
