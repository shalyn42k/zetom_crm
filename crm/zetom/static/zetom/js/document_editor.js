// claude — live preview on the document window
// (templates/admin/zetom/shared/document_change_form.html). Copies each form
// input into the matching [data-de-field] element of the paper preview while
// the user types; nothing is saved until the normal Save button is pressed.
(function () {
  "use strict";

  function formatValue(name, input) {
    var value = (input.value || "").trim();
    if (!value) return "";
    if (input.type === "date" || name === "deadline") {
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

  function init() {
    document.querySelectorAll("[data-de-preview]").forEach(bind);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
