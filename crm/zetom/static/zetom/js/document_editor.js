// claude — live preview on the document window
// (templates/admin/zetom/shared/document_change_form.html). Copies each form
// input into the matching [data-de-field] element of the paper preview while
// the user types; nothing is saved until the normal Save button is pressed.
(function () {
  "use strict";

  function formatValue(name, input) {
    var value = (input.value || "").trim();
    if (!value) return "";
    if (name === "extra_costs") {
      return money(parseFloat(value.replace(/\s/g, "").replace(",", ".")) || 0);
    }
    if (input.type === "date" || name === "deadline" || name === "offer_date") {
      // yyyy-mm-dd -> dd.mm.yyyy, same as the server-side |date:"d.m.Y"
      var m = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
      if (m) return m[3] + "." + m[2] + "." + m[1];
    }
    return value;
  }

  function bind(preview) {
    var form = document.getElementById(preview.dataset.deForm);
    if (!form) return;
    preview.querySelectorAll("[data-de-field]").forEach(function (target) {
      var name = target.dataset.deField;
      var input = form.querySelector('[name="' + name + '"]');
      if (!input) return;
      var update = function () {
        var text = formatValue(name, input);
        target.textContent = text || target.dataset.deEmpty || "";
        target.classList.toggle("de-empty", !text);
      };
      input.addEventListener("input", update);
      input.addEventListener("change", update);
      update();
    });
  }

  // ---- offer items (OfertaItem inline, prefix "items") -------------------
  // "1 350,00" — same grouping as the server-rendered |floatformat:"2g"
  function money(n) {
    var parts = (Math.round(n * 100) / 100).toFixed(2).split(".");
    return parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, "\u00a0") + "," + parts[1];
  }
  function num(v) {
    var x = parseFloat(String(v || "").replace(/\s/g, "").replace(",", "."));
    return isNaN(x) ? 0 : x;
  }
  function esc(t) {
    var d = document.createElement("div");
    d.textContent = t == null ? "" : String(t);
    return d.innerHTML;
  }

  function bindItems(preview, form) {
    var body = preview.querySelector("[data-de-items-body]");
    if (!body) return;
    var extraRow = body.querySelector(".of-extra");
    var val = function (name) {
      var el = form.querySelector('[name="' + name + '"]');
      return el ? el.value : "";
    };

    function rebuild() {
      var rows = [];
      form.querySelectorAll('[name^="items-"][name$="-name"]').forEach(function (inp) {
        var m = inp.name.match(/^items-(\d+)-name$/);
        if (!m) return;
        var p = "items-" + m[1] + "-";
        var del = form.querySelector('[name="' + p + 'DELETE"]');
        if (del && del.checked) return;
        if (!inp.value.trim()) return;
        var qty = num(val(p + "quantity")) || 0;
        var price = val(p + "unit_price");
        rows.push({
          pos: num(val(p + "position")), name: inp.value, details: val(p + "details"), norm: val(p + "norm"),
          qty: qty, price: price === "" ? null : num(price),
        });
      });
      rows.sort(function (a, b) { return a.pos - b.pos; });

      body.querySelectorAll("tr:not(.of-extra)").forEach(function (tr) { tr.remove(); });
      var total = 0;
      rows.forEach(function (r, i) {
        var line = (r.price || 0) * r.qty;
        total += line;
        var tr = document.createElement("tr");
        tr.innerHTML =
          '<td class="c-lp">' + (i + 1) + ".</td>" +
          '<td><div class="of-item">' + esc(r.name) + "</div>" +
          (r.details ? '<div class="of-item-details">' + esc(r.details) + "</div>" : "") +
          (r.norm ? '<div class="of-item-norm">' + esc(r.norm) + "</div>" : "") + "</td>" +
          '<td class="c-num">' + r.qty + "</td>" +
          '<td class="c-num">' + (r.price === null ? "—" : money(r.price)) + "</td>" +
          '<td class="c-num">' + money(line) + "</td>";
        body.insertBefore(tr, extraRow);
      });
      var lp = body.querySelector("[data-de-extra-lp]");
      if (lp) lp.textContent = (rows.length + 1) + ".";
      total += num(val("extra_costs"));
      preview.querySelectorAll("[data-de-total]").forEach(function (el) { el.textContent = money(total); });
    }

    form.addEventListener("input", rebuild);
    form.addEventListener("change", rebuild);
    new MutationObserver(rebuild).observe(form, { childList: true, subtree: true });
  }

  function init() {
    document.querySelectorAll("[data-de-preview]").forEach(function (preview) {
      bind(preview);
      var form = document.getElementById(preview.dataset.deForm);
      if (form) bindItems(preview, form);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
