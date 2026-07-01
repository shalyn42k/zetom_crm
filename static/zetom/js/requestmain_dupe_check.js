// claude
// Pre-save duplicate popup (redesign) — stepped modal, three sections.
//  Section 1 (dupes): rows built from check-duplicates JSON. Per-row pull
//    (copy into form) / del (soft-delete existing) / dismiss (hide row).
//    Plus a "Delete all duplicates" bulk button (soft, one POST).
//  Section 2 (clients): MULTI-SELECT checkboxes (popup_client_ids) + a
//    "create new" toggle (popup_create_new).
//  Section 3 (assignment): server-rendered departments + owners checkboxes.
// On "Save request": inject hidden inputs into the add form and submit it.
(function () {
  "use strict";

  var anchor, modal, form, checkUrl, dupActionUrl;
  var apiItems = [];
  var step = 1;
  var STEPS = 3;

  var badgeLabels = null;  // unused; badges arrive as [kind,label]

  function getCsrf() {
    var el = document.querySelector("[name=csrfmiddlewaretoken]");
    return el ? el.value : "";
  }

  function postForm(url, pairs) {
    var fd = new FormData();
    pairs.forEach(function (p) { fd.append(p[0], p[1]); });
    fd.append("csrfmiddlewaretoken", getCsrf());
    return fetch(url, { method: "POST", body: fd }).then(function (r) { return r.json(); });
  }

  function el(tag, cls) { var e = document.createElement(tag); if (cls) e.className = cls; return e; }

  function mb(b) {
    // b = [kind, label]
    var s = el("span", "mb " + b[0]);
    s.textContent = b[1];
    return s;
  }

  // ---- render duplicates ----
  function renderDupes(items) {
    var list = document.getElementById("rm-dupe-list");
    var empty = document.getElementById("rm-dupe-empty");
    var dupes = items.filter(function (it) { return it.type !== "client"; });
    list.innerHTML = "";
    if (!dupes.length) { empty.hidden = false; return; }
    empty.hidden = true;

    dupes.forEach(function (it) {
      var name = ((it.first_name || "") + " " + (it.last_name || "")).trim() || it.label || "—";
      var li = el("li", "dup" + (it.strong ? " strong" : ""));
      li.dataset.kind = it.type;
      li.dataset.pk = it.pk;

      var kind = el("span", "kind-badge " + it.type);
      kind.textContent = (it.type === "main" ? "M" : "N") + "#" + it.pk;
      li.appendChild(kind);

      var main = el("div", "dup-main");
      var top = el("div", "dup-top");
      var nm = el("span", "dup-name"); nm.textContent = name; top.appendChild(nm);
      if (it.company_name) { var co = el("span", "dup-co"); co.textContent = it.company_name; top.appendChild(co); }
      if (it.url) {
        var a = el("a", "dup-open"); a.href = it.url; a.target = "_blank"; a.title = "Open in new tab";
        a.innerHTML = '<svg class="i i-sm"><use href="#rmi-external"/></svg>';
        top.appendChild(a);
      }
      main.appendChild(top);
      var badges = el("div", "match-row");
      (it.badges || []).forEach(function (b) { badges.appendChild(mb(b)); });
      main.appendChild(badges);
      li.appendChild(main);

      var right = el("div", "dup-right");
      var score = el("div", "dup-score" + (it.score < 50 ? " weak" : ""));
      score.innerHTML = '<span class="n"><strong>' + it.score + '</strong>/100</span>'
        + '<span class="bar"><i style="width:' + it.score + '%"></i></span>';
      right.appendChild(score);
      var btns = el("div", "dup-btns");

      var pull = el("button", "mbtn"); pull.type = "button";
      pull.title = "Copy this record's fields into the form";
      pull.innerHTML = '<svg viewBox="0 0 24 24"><use href="#rmi-arrow-l"/></svg>pull';
      pull.addEventListener("click", function () {
        var map = { first_name: "id_first_name", last_name: "id_last_name",
                    phone: "id_phone", email: "id_email", company_name: "id_company_name" };
        Object.keys(map).forEach(function (k) {
          var f = document.getElementById(map[k]);
          if (f && it[k]) f.value = it[k];
        });
        li.style.opacity = ".45"; pull.disabled = true;
      });
      btns.appendChild(pull);

      var del = el("button", "mbtn del"); del.type = "button";
      del.title = it.type === "main" ? "Cancel this existing request" : "Soft-delete this record";
      del.innerHTML = '<svg viewBox="0 0 24 24"><use href="#rmi-trash"/></svg>del';
      del.addEventListener("click", function () {
        if (!confirm(del.title + "?")) return;
        postForm(dupActionUrl, [["action", "delete_existing:" + it.type + ":" + it.pk]])
          .then(function (d) { if (d && d.ok) { li.remove(); afterDupeRemoved(); } });
      });
      btns.appendChild(del);

      var dismiss = el("button", "mbtn icon"); dismiss.type = "button";
      dismiss.title = "Dismiss row (keep record)";
      dismiss.innerHTML = '<svg viewBox="0 0 24 24"><use href="#rmi-x"/></svg>';
      dismiss.addEventListener("click", function () { li.remove(); afterDupeRemoved(); });
      btns.appendChild(dismiss);

      right.appendChild(btns);
      li.appendChild(right);
      list.appendChild(li);
    });
  }

  function afterDupeRemoved() {
    var list = document.getElementById("rm-dupe-list");
    if (!list.children.length) document.getElementById("rm-dupe-empty").hidden = false;
    updateSummary();
  }

  // ---- render clients (multi-select) ----
  function renderClients(items) {
    var box = document.getElementById("rm-popup-clients");
    box.innerHTML = "";
    var clients = items.filter(function (it) { return it.type === "client"; });
    clients.forEach(function (it) {
      var name = ((it.first_name || "") + " " + (it.last_name || "")).trim() || it.label || "—";
      var hl = it.highlights || {};
      var label = el("label", "cli");
      var cb = el("input"); cb.type = "checkbox"; cb.name = "popup_client_ids"; cb.value = it.pk;
      cb.addEventListener("change", function () {
        label.classList.toggle("on", cb.checked);
        updateSummary();
      });
      label.appendChild(cb);
      var box2 = el("span", "cbx"); box2.innerHTML = '<svg viewBox="0 0 24 24"><use href="#rmi-check"/></svg>';
      label.appendChild(box2);

      var main = el("div", "cli-main");
      var top = el("div", "cli-top");
      top.innerHTML = '<span class="cli-name"></span>'
        + (it.company_name ? '<span class="cli-co"></span>' : '')
        + '<span class="cli-id mono">C-' + it.pk + '</span>';
      top.querySelector(".cli-name").textContent = name;
      if (it.company_name) top.querySelector(".cli-co").textContent = it.company_name;
      main.appendChild(top);

      var fields = el("div", "cli-fields");
      function f(k, v, on) {
        if (!v) return "";
        return '<div class="cli-f"><span class="k">' + k + '</span><span class="v mono">'
          + (on ? '<span class="hl">' + v + '</span>' : v) + '</span></div>';
      }
      fields.innerHTML = f("phone", it.phone, hl.phone) + f("email", it.email, hl.email) + f("nip", it.company_nip, hl.company_nip);
      main.appendChild(fields);

      var badges = el("div", "match-row");
      (it.badges || []).forEach(function (b) { badges.appendChild(mb(b)); });
      main.appendChild(badges);
      label.appendChild(main);

      var sc = el("div", "cli-score");
      sc.innerHTML = '<span class="n"><strong>' + it.score + '</strong>/100</span>'
        + '<span class="bar"><i style="width:' + it.score + '%"></i></span>';
      label.appendChild(sc);
      box.appendChild(label);
    });
  }

  // ---- summary line ----
  function updateSummary() {
    var dupes = document.querySelectorAll("#rm-dupe-list .dup").length;
    var n = document.querySelectorAll("#rm-popup-clients .cli input:checked").length;
    var creating = document.getElementById("popup_create_new").checked;
    var cl = n + " client" + (n === 1 ? "" : "s") + (creating ? " + new" : "");
    document.getElementById("rm-foot-sum").textContent = dupes + " dupes · " + cl;
  }

  // ---- collect + submit ----
  function proceed() {
    form.querySelectorAll(".rm-popup-hidden").forEach(function (e) { e.remove(); });
    function addHidden(name, value) {
      var h = document.createElement("input");
      h.type = "hidden"; h.name = name; h.value = value; h.className = "rm-popup-hidden";
      form.appendChild(h);
    }
    modal.querySelectorAll("#rm-popup-clients input:checked").forEach(function (cb) {
      addHidden("popup_client_ids", cb.value);
    });
    if (document.getElementById("popup_create_new").checked) addHidden("popup_create_new", "1");
    modal.querySelectorAll("[name=popup_departments]:checked").forEach(function (cb) {
      addHidden("popup_departments", cb.value);
    });
    modal.querySelectorAll("[name=popup_owners]:checked").forEach(function (cb) {
      addHidden("popup_owners", cb.value);
    });
    form.dataset.dupeConfirmed = "1";
    if (form.requestSubmit) form.requestSubmit(window._rmPendingSubmitter || undefined);
    else form.submit();
  }

  // ---- wizard nav ----
  function goto(n) {
    step = Math.max(1, Math.min(STEPS, n));
    modal.querySelectorAll(".rm-sec").forEach(function (s) { s.classList.toggle("active", +s.dataset.step === step); });
    modal.querySelectorAll(".rm-step").forEach(function (t) {
      var k = +t.dataset.step;
      t.classList.toggle("active", k === step);
      t.classList.toggle("done", k < step);
    });
    document.getElementById("rm-back").style.visibility = step > 1 ? "visible" : "hidden";
    document.getElementById("rm-next").hidden = step === STEPS;
    document.getElementById("rm-dupe-proceed").hidden = step !== STEPS;
    var body = modal.querySelector(".rm-body"); if (body) body.scrollTop = 0;
  }

  // ---- open / close ----
  var lastFocus = null;
  function open() { lastFocus = document.activeElement; modal.classList.add("open"); modal.querySelector(".hx").focus(); }
  function close() { modal.classList.remove("open"); if (lastFocus) lastFocus.focus(); }

  function collectParams() {
    var map = { first_name: "id_first_name", last_name: "id_last_name", phone: "id_phone",
                email: "id_email", company_name: "id_company_name", company_nip: "id_company_nip" };
    var params = new URLSearchParams();
    Object.keys(map).forEach(function (k) {
      var f = document.getElementById(map[k]);
      if (f && f.value) params.set(k, f.value);
    });
    return params.toString();
  }

  document.addEventListener("DOMContentLoaded", function () {
    anchor = document.getElementById("rm-dupe-check");
    modal = document.getElementById("rm-dupe-modal");
    if (!anchor || !modal) return;
    form = document.getElementById(anchor.dataset.formId);
    if (!form) return;
    checkUrl = anchor.dataset.url;
    dupActionUrl = anchor.dataset.dupActionUrl;

    // Reparent the modal to <body> so position:fixed anchors to the viewport.
    // Inside the Unfold content column a transformed ancestor makes fixed
    // behave like absolute, pinning the modal off-centre. The modal's own
    // inputs are read by pk and copied into the form on submit, so moving it
    // out of the content flow is safe.
    document.body.appendChild(modal);

    document.getElementById("rm-dupe-cancel").addEventListener("click", close);
    document.getElementById("rm-dupe-x").addEventListener("click", close);
    document.getElementById("rm-dupe-proceed").addEventListener("click", proceed);
    document.getElementById("rm-back").addEventListener("click", function () { goto(step - 1); });
    document.getElementById("rm-next").addEventListener("click", function () { goto(step + 1); });
    modal.querySelectorAll(".rm-step").forEach(function (t) {
      t.addEventListener("click", function () { goto(+t.dataset.step); });
    });
    modal.addEventListener("mousedown", function (e) { if (e.target === modal) close(); });
    document.addEventListener("keydown", function (e) {
      if (!modal.classList.contains("open")) return;
      if (e.key === "Escape") { close(); return; }
      if (e.key === "Tab") {
        var box = modal.querySelector(".rm-modal");
        var f = [].slice.call(box.querySelectorAll('button,input,a,[tabindex]:not([tabindex="-1"])'))
          .filter(function (x) { return !x.disabled && x.offsetParent !== null; });
        if (!f.length) return;
        var first = f[0], last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    });

    // Delete-all-duplicates (bulk, soft).
    document.getElementById("rm-dupe-delete-all").addEventListener("click", function () {
      var rows = [].slice.call(document.querySelectorAll("#rm-dupe-list .dup"));
      if (!rows.length) return;
      if (!confirm("Move all duplicates to trash / cancel them? This can be undone.")) return;
      var pairs = [["action", "delete_all_dupes"]];
      rows.forEach(function (r) { pairs.push(["targets", r.dataset.kind + ":" + r.dataset.pk]); });
      postForm(dupActionUrl, pairs).then(function (d) {
        if (d && d.ok) {
          document.getElementById("rm-dupe-list").innerHTML = "";
          document.getElementById("rm-dupe-empty").hidden = false;
          updateSummary();
        }
      });
    });

    // Create-new toggle.
    document.getElementById("popup_create_new").addEventListener("change", function () {
      document.getElementById("rm-create-toggle").classList.toggle("on", this.checked);
      updateSummary();
    });

    // Assignment chips / owners.
    modal.querySelectorAll("#popup-dep-group .dchip input").forEach(function (i) {
      i.addEventListener("change", function () { this.closest(".dchip").classList.toggle("on", this.checked); });
    });
    modal.querySelectorAll("#popup-owner-list .orow input").forEach(function (i) {
      i.addEventListener("change", function () { this.closest(".orow").classList.toggle("on", this.checked); });
    });

    // Intercept add-form save → run duplicate check.
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
          updateSummary();
          goto(1);
          open();
        })
        .catch(function () {
          alert("Network error — could not check for duplicates. Check connection and try again.");
        });
    });
  });
})();
