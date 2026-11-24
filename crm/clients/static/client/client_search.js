document.addEventListener("DOMContentLoaded", function () {
    const input = document.querySelector("#id_company_name");
    if (!input) return;

    const dropdown = document.createElement("div");
    dropdown.className = "autocomplete-dropdown";
    dropdown.style.position = "absolute";
    dropdown.style.background = "#1e1e1e";
    dropdown.style.border = "1px solid #444";
    dropdown.style.width = input.offsetWidth + "px";
    dropdown.style.zIndex = 9999;
    dropdown.style.display = "none";

    input.parentNode.appendChild(dropdown);

    let timer = null;

    input.addEventListener("input", function () {
        const q = input.value.trim();
        if (!q) {
            dropdown.style.display = "none";
            return;
        }

        clearTimeout(timer);
        timer = setTimeout(() => {
            fetch(`/clients/search/?q=${encodeURIComponent(q)}`)
                .then(r => r.json())
                .then(data => {
                    dropdown.innerHTML = "";
                    if (!data.results.length) {
                        dropdown.style.display = "none";
                        return;
                    }

                    // claude — the endpoint sends company_nip/company_name;
                    // reading `client.nip` here put the literal "undefined"
                    // into the NIP field and rendered "(undefined)" in the
                    // dropdown label.
                    const setField = (selector, value) => {
                        const field = document.querySelector(selector);
                        if (field) field.value = value || "";
                    };

                    data.results.forEach(client => {
                        const item = document.createElement("div");
                        item.className = "autocomplete-item";
                        item.style.padding = "6px 10px";
                        item.style.cursor = "pointer";
                        item.style.borderBottom = "1px solid #333";
                        item.innerText = client.company_nip
                            ? `${client.label} (${client.company_nip})`
                            : client.label;

                        item.addEventListener("click", () => {
                            dropdown.style.display = "none";

                            // автозаполнение
                            setField("#id_company_name", client.company_name || client.label);
                            setField("#id_company_nip", client.company_nip);
                            setField("#id_first_name", client.first_name);
                            setField("#id_last_name", client.last_name);
                            setField("#id_email", client.email);
                            setField("#id_phone", client.phone);
                            setField("#id_address", client.address);
                        });

                        dropdown.appendChild(item);
                    });

                    dropdown.style.display = "block";
                });
        }, 300);
    });

    document.addEventListener("click", function (e) {
        if (!dropdown.contains(e.target) && e.target !== input) {
            dropdown.style.display = "none";
        }
    });
});
