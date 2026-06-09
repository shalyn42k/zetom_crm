// claude
// Fetch-based client link/unlink/create for the client card.
// All actions POST via fetch, update DOM without page reload.
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
    row.innerHTML = '<span class="rm-linked-name">' + cl.label + "</span>" +
      (cl.nip ? '<span class="rm-linked-nip mono">NIP ' + cl.nip + "</span>" : "") +
      '<button type="button" class="rm-linked-x js-unlink-client" data-client="' + cl.pk + '" data-url="' + unlinkBase + '" title="Unlink">×</button>';
    return row;
  }

  document.addEventListener("DOMContentLoaded", function () {
    var card = document.getElementById("client-card");
    if (!card || !card.dataset.pk) return; // add view — nothing to wire

    var list = document.getElementById("rm-linked-list");
    var empty = document.getElementById("rm-linked-empty");
    var suggestions = document.getElementById("rm-suggestions");
    var select = document.getElementById("id_client"); // form.client field doubles as linker
    var linkBtn = document.getElementById("rm-linker-btn");
    var createBtn = document.getElementById("rm-create-btn");
    var status = document.getElementById("rm-link-status");

    function hideEmpty() {
      if (empty) empty.hidden = true;
      if (suggestions) suggestions.style.display = "none";
    }

    // Unlink (delegated, handles both pre-rendered and dynamic rows)
    list.addEventListener("click", function (e) {
      var btn = e.target.closest(".js-unlink-client");
      if (!btn) return;
      var pk = parseInt(btn.dataset.client, 10);
      if (!pk) return;
      var base = card.dataset.unlinkUrl;
      var url = btn.dataset.url || base.replace("/0/", "/" + pk + "/");
      postJson(url)
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d.ok) {
            var row = list.querySelector('[data-client-pk="' + pk + '"]');
            if (row) row.remove();
            // restore empty label if no rows left
            var remaining = list.querySelectorAll(".rm-linked-row");
            if (!remaining.length && empty) empty.hidden = false;
            showStatus(status, "Unlinked.", true);
          }
        });
    });

    // Suggestion quick-link
    if (suggestions) {
      suggestions.addEventListener("click", function (e) {
        var btn = e.target.closest(".js-link-client");
        if (!btn) return;
        var pk = btn.dataset.client;
        var base = card.dataset.linkUrl;
        var url = base.replace("/0/", "/" + pk + "/");
        postJson(url)
          .then(function (r) { return r.json(); })
          .then(function (d) {
            if (d.ok) {
              var row = buildLinkedRow(d, card);
              // insert before empty placeholder
              if (empty) list.insertBefore(row, empty);
              else list.appendChild(row);
              hideEmpty();
              btn.closest(".rm-suggestion-row").remove();
              showStatus(status, "Linked.", true);
            }
          });
      });
    }

    // Select → link (form.client field drives both FK autofill and M2M link)
    if (linkBtn && select) {
      linkBtn.addEventListener("click", function () {
        var pk = select.value;
        if (!pk) return;
        var base = card.dataset.linkUrl;
        var url = base.replace("/0/", "/" + pk + "/");
        postJson(url)
          .then(function (r) { return r.json(); })
          .then(function (d) {
            if (d.ok) {
              if (!d.created) { showStatus(status, "Already linked.", true); return; }
              var row = buildLinkedRow(d, card);
              if (empty) list.insertBefore(row, empty);
              else list.appendChild(row);
              hideEmpty();
              // don't remove option — form.client FK field still needs it for autofill save
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
  });
})();
