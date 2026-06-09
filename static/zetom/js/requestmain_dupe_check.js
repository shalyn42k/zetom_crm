// claude
// Pre-save duplicate popup — multi-step mini-VW (steps 02 / 03 / 04).
// Step 02: dup list with per-row fetch actions (delete existing / pull into form / dismiss).
// Step 03: client candidates radio-select → stores popup_client_choice.
// Step 04: departments + owners checkboxes → stored as popup_departments / popup_owners.
// On "Save": adds hidden inputs to the form then submits.
(function () {
  "use strict";

  var anchor, modal, form, checkUrl, dupActionUrl;
  var currentStep = 2;
  var clientChoice = "unlinked"; // "link:<pk>" | "create" | "unlinked"
  var apiItems = [];   // raw response from check-duplicates

  function getCsrf() {
    var el = document.querySelector("[name=csrfmiddlewaretoken]");
    return el ? el.value : "";
  }

  function postJson(url, data) {
    var fd = new FormData();
    Object.keys(data || {}).forEach(function (k) { fd.append(k, data[k]); });
    fd.append("csrfmiddlewaretoken", getCsrf());
    return fetch(url, { method: "POST", body: fd }).then(function (r) { return r.json(); });
  }

  // ---- Step navigation ----
  function goTo(step) {
    currentStep = step;
    modal.querySelectorAll(".rm-popup-section").forEach(function (s) {
      s.hidden = parseInt(s.dataset.section, 10) !== step;
    });
    modal.querySelectorAll(".rm-popup-step").forEach(function (b) {
      b.classList.toggle("active", parseInt(b.dataset.step, 10) === step);
    });
    var prev = document.getElementById("rm-popup-prev");
    var next = document.getElementById("rm-popup-next");
    var proceed = document.getElementById("rm-dupe-proceed");
    prev.hidden = (step === 2);
    next.hidden = (step === 4);
    proceed.hidden = (step !== 4);
  }

  // ---- Render step 02: dup rows ----
  function renderDupes(items) {
    var list = document.getElementById("rm-dupe-list");
    var empty = document.getElementById("rm-dupe-empty");
    var dupes = items.filter(function (it) { return it.type !== "client"; });
    list.innerHTML = "";
    if (!dupes.length) { empty.hidden = false; return; }
    empty.hidden = true;
    dupes.forEach(function (it) {
      var li = document.createElement("li");
      li.className = "rm-dupe-modal__item";
      li.dataset.pk = it.pk;
      li.dataset.type = it.type;

      var kindEl = document.createElement("span");
      kindEl.className = "rm-dupe-modal__kind " + it.type;
      kindEl.textContent = (it.type === "main" ? "M" : "N") + "#" + it.pk;
      li.appendChild(kindEl);

      var labelEl = document.createElement("span");
      labelEl.className = "rm-dupe-modal__label";
      labelEl.textContent = it.label;
      li.appendChild(labelEl);

      (it.badges || []).forEach(function (b) {
        var s = document.createElement("span");
        s.className = "rm-dupe-modal__badge";
        s.textContent = b;
        li.appendChild(s);
      });

      var scoreEl = document.createElement("span");
      scoreEl.className = "rm-dupe-modal__score";
      scoreEl.textContent = it.score + "/100";
      li.appendChild(scoreEl);

      if (it.url) {
        var a = document.createElement("a");
        a.className = "rm-dupe-modal__open";
        a.href = it.url;
        a.target = "_blank";
        a.textContent = "↗";
        li.appendChild(a);
      }

      // pull info into form (pure JS, no server call)
      var pullBtn = document.createElement("button");
      pullBtn.type = "button";
      pullBtn.className = "rm-dupe-modal__act";
      pullBtn.textContent = "← pull";
      pullBtn.title = "Copy this record’s data into the form";
      pullBtn.addEventListener("click", function () {
        var map = { first_name:"id_first_name", last_name:"id_last_name",
                    phone:"id_phone", email:"id_email", company_name:"id_company_name" };
        Object.keys(map).forEach(function (k) {
          var el = document.getElementById(map[k]);
          if (el && it[k]) el.value = it[k];
        });
        li.style.opacity = ".4";
        pullBtn.disabled = true;
      });
      li.appendChild(pullBtn);

      // delete existing
      var delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.className = "rm-dupe-modal__act danger";
      delBtn.textContent = "del";
      delBtn.title = it.type === "main" ? "Cancel this existing request" : "Hard-delete this validation request";
      delBtn.addEventListener("click", function () {
        if (!confirm(delBtn.title + "?")) return;
        postJson(dupActionUrl, { action: "delete_existing:" + it.type + ":" + it.pk })
          .then(function (d) {
            if (d.ok) {
              li.remove();
              if (!list.children.length) empty.hidden = false;
            }
          });
      });
      li.appendChild(delBtn);

      // dismiss (hide row, keep record)
      var dimBtn = document.createElement("button");
      dimBtn.type = "button";
      dimBtn.className = "rm-dupe-modal__act";
      dimBtn.textContent = "×";
      dimBtn.title = "Dismiss (keep existing record)";
      dimBtn.addEventListener("click", function () { li.remove(); if (!list.children.length) empty.hidden = false; });
      li.appendChild(dimBtn);

      list.appendChild(li);
    });
  }

  // ---- Render step 03: client candidates ----
  function renderClients(items) {
    var container = document.getElementById("rm-popup-clients");
    container.innerHTML = "";
    var clients = items.filter(function (it) { return it.type === "client"; });
    if (!clients.length) return;
    clients.forEach(function (it) {
      var label = document.createElement("label");
      label.className = "rm-popup-opt";
      var radio = document.createElement("input");
      radio.type = "radio";
      radio.name = "popup_client_internal";
      radio.value = "link:" + it.pk;
      var text = document.createElement("span");
      text.textContent = it.label;
      var badges = document.createElement("span");
      badges.className = "rm-sug-badges";
      (it.badges || []).forEach(function (b) {
        var s = document.createElement("span");
        s.className = "rm-dupe-modal__badge";
        s.textContent = b;
        badges.appendChild(s);
      });
      var score = document.createElement("span");
      score.className = "rm-dupe-modal__score";
      score.textContent = it.score + "/100";
      label.appendChild(radio);
      label.appendChild(text);
      label.appendChild(badges);
      label.appendChild(score);
      container.appendChild(label);
    });
  }

  // ---- Collect choices and submit ----
  function proceed() {
    // Read client choice from radios
    var radios = modal.querySelectorAll("[name=popup_client_internal]");
    radios.forEach(function (r) { if (r.checked) clientChoice = r.value; });

    // Add hidden inputs to form
    var existing = form.querySelectorAll(".rm-popup-hidden");
    existing.forEach(function (e) { e.remove(); });

    function addHidden(name, value) {
      var h = document.createElement("input");
      h.type = "hidden";
      h.name = name;
      h.value = value;
      h.className = "rm-popup-hidden";
      form.appendChild(h);
    }

    addHidden("popup_client_choice", clientChoice);

    modal.querySelectorAll("[name=popup_departments]:checked").forEach(function (cb) {
      addHidden("popup_departments", cb.value);
    });
    modal.querySelectorAll("[name=popup_owners]:checked").forEach(function (cb) {
      addHidden("popup_owners", cb.value);
    });

    form.dataset.dupeConfirmed = "1";
    if (form.requestSubmit) { form.requestSubmit(window._rmPendingSubmitter || undefined); }
    else { form.submit(); }
  }

  // ---- Bootstrap ----
  document.addEventListener("DOMContentLoaded", function () {
    anchor = document.getElementById("rm-dupe-check");
    modal = document.getElementById("rm-dupe-modal");
    if (!anchor || !modal) return;

    form = document.getElementById(anchor.dataset.formId);
    if (!form) return;

    checkUrl = anchor.dataset.url;
    dupActionUrl = anchor.dataset.dupActionUrl;

    var btnCancel = document.getElementById("rm-dupe-cancel");
    var btnPrev = document.getElementById("rm-popup-prev");
    var btnNext = document.getElementById("rm-popup-next");
    var btnProceed = document.getElementById("rm-dupe-proceed");

    btnCancel.addEventListener("click", function () { modal.hidden = true; });
    modal.addEventListener("click", function (e) { if (e.target === modal) modal.hidden = true; });

    btnPrev.addEventListener("click", function () { goTo(currentStep - 1); });
    btnNext.addEventListener("click", function () { goTo(currentStep + 1); });
    btnProceed.addEventListener("click", proceed);

    // Step nav tabs
    modal.querySelectorAll(".rm-popup-step").forEach(function (btn) {
      btn.addEventListener("click", function () { goTo(parseInt(btn.dataset.step, 10)); });
    });

    // Intercept form save
    form.addEventListener("submit", function (e) {
      if (form.dataset.dupeConfirmed === "1") return;
      e.preventDefault();
      window._rmPendingSubmitter = e.submitter || null;

      fetch(checkUrl + "?" + collectParams(), { headers: { "X-Requested-With": "XMLHttpRequest" } })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (!data || !data.count) { proceed(); return; }
          apiItems = data.items || [];
          renderDupes(apiItems);
          renderClients(apiItems);
          goTo(2);
          modal.hidden = false;
        })
        .catch(function () {
          alert("Network error — could not check for duplicates. Check connection and try again.");
        });
    });
  });

  function collectParams() {
    var map = { first_name:"id_first_name", last_name:"id_last_name",
                phone:"id_phone", email:"id_email",
                company_name:"id_company_name", company_nip:"id_company_nip" };
    var params = new URLSearchParams();
    Object.keys(map).forEach(function (k) {
      var el = document.getElementById(map[k]);
      if (el && el.value) params.set(k, el.value);
    });
    return params.toString();
  }
})();
