// Fetch-based client link/unlink/create for the client card.
// Edit client opens modal with fields, saves via fetch without page reload.
// All link/unlink/create actions POST via fetch, update DOM without page reload.
// URLs are injected via data- attributes on #client-card.
(function () {
  "use strict";

  function getCsrf() {
    var el = document.querySelector("[name=csrfmiddlewaretoken]");
    return el ? el.value : "";
  }

  function postJson(url, data) {
    var fd = new FormData();
    Object.keys(data || {}).forEach(function (k) { fd.append(k, data[k]); });
    fd.append("csrfmiddlewaretoken", getCsrf());
    return fetch(url, { method: "POST", body: fd });
  }

  function showStatus(el, msg, ok) {
    if (!el) return;
    el.textContent = msg;
    el.className = "rm-link-status " + (ok ? "ok" : "err");
    el.hidden = false;
    setTimeout(function () { el.hidden = true; }, 3000);
  }

  function buildLinkedRow(cl, card) {
    var unlinkBase = card.dataset.unlinkUrl.replace("/0/", "/" + cl.pk + "/");
    var row = document.createElement("div");
    row.className = "rm-linked-row";
    row.dataset.clientPk = cl.pk;
    row.innerHTML =
      '<a class="rm-linked-name" href="/admin/clients/client/' + cl.pk + '/change/" target="_blank">' + cl.label + "</a>" +
      (cl.nip ? '<span class="rm-linked-nip mono">NIP ' + cl.nip + "</span>" : "") +
      '<button type="button" class="rm-linked-edit js-edit-client" data-client="' + cl.pk + '" title="Edit">\u270e</button>' +
      '<button type="button" class="rm-linked-x js-unlink-client" data-client="' + cl.pk + '" data-url="' + unlinkBase + '" title="Unlink">\u00d7</button>';
    return row;
  }

  function buildEditFormHtml(data) {
    function field(label, name, type, value) {
      return '<div class="rm-form-group">' +
        '<label class="rm-label">' + label + '</label>' +
        '<input type="' + type + '" name="' + name + '" value="' + escapeHtml(value) + '" class="rm-form-input">' +
        '</div>';
    }
    // claude — phase 3c: person-only editor. Company (name/NIP) is read-only
    // here — it lives on the linked Company, edited on the Company card.
    function companyRow() {
      if (!data.company_name && !data.company_nip) return "";
      var txt = data.company_name || "";
      if (data.company_nip) txt += (txt ? " · " : "") + "NIP " + data.company_nip;
      return '<div class="rm-form-group">' +
        '<label class="rm-label">Firma</label>' +
        '<div class="rm-form-ro">' + escapeHtml(txt) + '</div>' +
        '</div>';
    }
    return field("First name", "first_name", "text", data.first_name) +
      field("Last name", "last_name", "text", data.last_name) +
      companyRow() +
      field("Phone", "phone", "text", data.phone) +
      field("Email", "email", "email", data.email) +
      field("Address", "address", "text", data.address);
  }

  function escapeHtml(text) {
    var div = document.createElement("div");
    div.textContent = text || "";
    return div.innerHTML;
  }

  document.addEventListener("DOMContentLoaded", function () {
    var card = document.getElementById("client-card");
    if (!card || !card.dataset.pk) return;

    var list         = document.getElementById("rm-linked-list");
    var empty        = document.getElementById("rm-linked-empty");
    var suggestions  = document.getElementById("rm-suggestions");
    var select       = document.getElementById("id_client");
    var linkBtn      = document.getElementById("rm-linker-btn");
    var createBtn    = document.getElementById("rm-create-btn");
    var status       = document.getElementById("rm-link-status");
    var modal        = document.getElementById("rm-edit-client-modal");
    var modalBody    = document.getElementById("rm-modal-body");
    var modalOverlay = document.getElementById("rm-modal-overlay");
    var modalClose   = document.getElementById("rm-modal-close");
    var modalCancel  = document.getElementById("rm-modal-cancel");
    var modalSave    = document.getElementById("rm-modal-save");
    var currentEditingClientId = null;
    var currentEditingSaveUrl  = null;

    function hideEmpty() {
      if (empty) empty.hidden = true;
      if (suggestions) suggestions.style.display = "none";
    }

    function closeModal() {
      if (modal) {
        modal.hidden = true;
        modalBody.innerHTML = "";
        currentEditingClientId = null;
        currentEditingSaveUrl  = null;
      }
    }

    // Edit client — fetch data, show modal with form
    if (list) {
      list.addEventListener("click", function (e) {
        var btn = e.target.closest(".js-edit-client");
        if (!btn) return;
        var pk = parseInt(btn.dataset.client, 10);
        if (!pk) return;
        var editUrl = card.dataset.editUrl.replace("/0/", "/" + pk + "/");
        var saveUrl = card.dataset.saveUrl.replace("/0/", "/" + pk + "/");
        fetch(editUrl)
          .then(function (r) { return r.json(); })
          .then(function (d) {
            if (d.ok) {
              currentEditingClientId = pk;
              currentEditingSaveUrl  = saveUrl;
              modalBody.innerHTML = buildEditFormHtml(d);
              if (modal) modal.hidden = false;
            } else {
              alert("Error loading client data");
            }
          });
      });
    }

    // Unlink (delegated)
    if (list) {
      list.addEventListener("click", function (e) {
        var btn = e.target.closest(".js-unlink-client");
        if (!btn) return;
        var pk  = parseInt(btn.dataset.client, 10);
        if (!pk) return;
        var base = card.dataset.unlinkUrl;
        var url  = btn.dataset.url || base.replace("/0/", "/" + pk + "/");
        postJson(url)
          .then(function (r) { return r.json(); })
          .then(function (d) {
            if (d.ok) {
              var row = list.querySelector('[data-client-pk="' + pk + '"]');
              if (row) row.remove();
              var remaining = list.querySelectorAll(".rm-linked-row");
              if (!remaining.length && empty) empty.hidden = false;
              showStatus(status, "Unlinked.", true);
            }
          });
      });
    }

    // Suggestion quick-link
    if (suggestions) {
      suggestions.addEventListener("click", function (e) {
        var btn = e.target.closest(".js-link-client");
        if (!btn) return;
        var pk  = btn.dataset.client;
        var url = card.dataset.linkUrl.replace("/0/", "/" + pk + "/");
        postJson(url)
          .then(function (r) { return r.json(); })
          .then(function (d) {
            if (d.ok) {
              var row = buildLinkedRow(d, card);
              if (empty) list.insertBefore(row, empty);
              else list.appendChild(row);
              hideEmpty();
              btn.closest(".rm-suggestion-row").remove();
              showStatus(status, "Linked.", true);
            }
          });
      });
    }

    // Select -> link
    if (linkBtn && select) {
      linkBtn.addEventListener("click", function () {
        var pk = select.value;
        if (!pk) return;
        var url = card.dataset.linkUrl.replace("/0/", "/" + pk + "/");
        postJson(url)
          .then(function (r) { return r.json(); })
          .then(function (d) {
            if (d.ok) {
              if (!d.created) { showStatus(status, "Already linked.", true); return; }
              var row = buildLinkedRow(d, card);
              if (empty) list.insertBefore(row, empty);
              else list.appendChild(row);
              hideEmpty();
              showStatus(status, "Linked.", true);
            } else {
              showStatus(status, "Error.", false);
            }
          });
      });
    }

    // Create from request
    if (createBtn) {
      createBtn.addEventListener("click", function () {
        postJson(card.dataset.createUrl)
          .then(function (r) { return r.json(); })
          .then(function (d) {
            if (d.ok) {
              var row = buildLinkedRow(d, card);
              if (empty) list.insertBefore(row, empty);
              else list.appendChild(row);
              hideEmpty();
              showStatus(status, "Created and linked.", true);
              createBtn.disabled = true;
            } else {
              showStatus(status, "Error.", false);
            }
          });
      });
    }

    // Modal controls
    if (modal) {
      modalClose.addEventListener("click", closeModal);
      modalOverlay.addEventListener("click", closeModal);
      modalCancel.addEventListener("click", closeModal);

      modalSave.addEventListener("click", function () {
        if (!currentEditingSaveUrl) return;
        var data = {};
        modalBody.querySelectorAll("input").forEach(function (inp) {
          data[inp.name] = inp.value;
        });
        postJson(currentEditingSaveUrl, data)
          .then(function (r) { return r.json(); })
          .then(function (d) {
            if (d.ok) {
              // Update linked-client row label
              var row = list.querySelector('[data-client-pk="' + currentEditingClientId + '"]');
              if (row) {
                var nameEl = row.querySelector(".rm-linked-name");
                if (nameEl) nameEl.textContent = d.label;
                var nipEl = row.querySelector(".rm-linked-nip");
                if (nipEl) nipEl.textContent = d.nip ? "NIP " + d.nip : "";
              }
              // claude — phase 3c: sync only person fields to the RequestMain
              // form; the request keeps its own company snapshot (not edited
              // through the person editor).
              var fieldMap = {
                "id_first_name":   d.first_name,
                "id_last_name":    d.last_name,
                "id_email":        d.email,
                "id_phone":        d.phone,
              };
              Object.keys(fieldMap).forEach(function (id) {
                var el = document.getElementById(id);
                if (el) el.value = fieldMap[id] || "";
              });
              closeModal();
              showStatus(status, "Client updated.", true);
            } else {
              alert("Error saving client: " + (d.error || "Unknown error"));
            }
          });
      });
    }
  });
})();