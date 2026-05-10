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

                    data.results.forEach(client => {
                        const item = document.createElement("div");
                        item.className = "autocomplete-item";
                        item.style.padding = "6px 10px";
                        item.style.cursor = "pointer";
                        item.style.borderBottom = "1px solid #333";
                        item.innerText = `${client.label} (${client.nip})`;

                        item.addEventListener("click", () => {
                            dropdown.style.display = "none";

                            // автозаполнение
                            document.querySelector("#id_company_name").value = client.label;
                            document.querySelector("#id_company_nip").value = client.nip;
                            document.querySelector("#id_first_name").value = client.first_name || "";
                            document.querySelector("#id_last_name").value = client.last_name || "";
                            document.querySelector("#id_email").value = client.email || "";
                            document.querySelector("#id_phone").value = client.phone || "";
                            document.querySelector("#id_address").value = client.address || "";
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
