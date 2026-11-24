// claude — searchable dropdown for long <select>s (users, departments, …).
//
// Progressive enhancement: any <select data-combobox> gets a text box above a
// filtered list; the <select> stays in the DOM (hidden) and keeps the value,
// so form posts, formaction buttons and server code don't change at all.
// Keyboard: ↑/↓ move, Enter picks, Esc closes. Styles: static/admin/css/combobox.css.
// The client picker (crm/clients/static/client/client_picker.js) uses the same
// list markup via window.zetomCombobox.renderList.
(function () {
  "use strict";

  function escapeHtml(text) {
    var div = document.createElement("div");
    div.textContent = text == null ? "" : String(text);
    return div.innerHTML;
  }

  function highlight(text, query) {
    var safe = escapeHtml(text);
    if (!query) return safe;
    var idx = String(text).toLowerCase().indexOf(query.toLowerCase());
    if (idx < 0) return safe;
    return escapeHtml(text.slice(0, idx)) + "<mark>" + escapeHtml(text.slice(idx, idx + query.length)) +
      "</mark>" + escapeHtml(text.slice(idx + query.length));
  }

  // items: [{main, sub, value}] ; onPick(item) ; returns nothing
  function renderList(list, items, query, emptyText) {
    list.innerHTML = "";
    if (!items.length) {
      var li = document.createElement("li");
      li.className = "cbx__empty";
      li.textContent = emptyText;
      list.appendChild(li);
      return;
    }
    items.forEach(function (item, i) {
      var li = document.createElement("li");
      li.className = "cbx__opt";
      li.setAttribute("role", "option");
      li.dataset.index = i;
      li.setAttribute("aria-selected", i === 0 ? "true" : "false");
      li.innerHTML = '<span class="cbx__opt-main">' + highlight(item.main, query) + "</span>" +
        (item.sub ? '<span class="cbx__opt-sub">' + highlight(item.sub, query) + "</span>" : "");
      list.appendChild(li);
    });
  }

  function moveActive(list, step) {
    var opts = list.querySelectorAll(".cbx__opt");
    if (!opts.length) return;
    var cur = Array.prototype.findIndex.call(opts, function (o) { return o.getAttribute("aria-selected") === "true"; });
    var next = Math.max(0, Math.min(opts.length - 1, cur + step));
    opts.forEach(function (o, i) { o.setAttribute("aria-selected", i === next ? "true" : "false"); });
    opts[next].scrollIntoView({ block: "nearest" });
  }

  function activeIndex(list) {
    var el = list.querySelector('.cbx__opt[aria-selected="true"]');
    return el ? parseInt(el.dataset.index, 10) : -1;
  }

  function enhanceSelect(select) {
    if (select.dataset.cbxReady) return;
    select.dataset.cbxReady = "1";
    var emptyText = select.dataset.comboboxEmpty || "—";

    var wrap = document.createElement("div");
    wrap.className = "cbx";
    var input = document.createElement("input");
    input.type = "text";
    input.className = "cbx__input";
    input.autocomplete = "off";
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-expanded", "false");
    input.placeholder = select.dataset.comboboxPlaceholder || "";
    var list = document.createElement("ul");
    list.className = "cbx__list";
    list.setAttribute("role", "listbox");
    list.hidden = true;

    select.parentNode.insertBefore(wrap, select);
    wrap.appendChild(input);
    wrap.appendChild(list);
    wrap.appendChild(select);
    select.hidden = true;
    select.tabIndex = -1;

    var current = [];
    function options() {
      return Array.prototype.filter.call(select.options, function (o) { return o.value !== ""; })
        .map(function (o) { return { main: o.textContent.trim(), sub: o.dataset.sub || "", value: o.value }; });
    }
    function syncLabel() {
      var opt = select.options[select.selectedIndex];
      input.value = opt && opt.value !== "" ? opt.textContent.trim() : "";
    }
    function open(query) {
      var q = (query || "").trim().toLowerCase();
      current = options().filter(function (it) {
        return !q || it.main.toLowerCase().indexOf(q) >= 0 || it.sub.toLowerCase().indexOf(q) >= 0;
      });
      renderList(list, current, query && query.trim(), emptyText);
      list.hidden = false;
      input.setAttribute("aria-expanded", "true");
    }
    function close() {
      list.hidden = true;
      input.setAttribute("aria-expanded", "false");
    }
    function pick(i) {
      var item = current[i];
      if (!item) return;
      select.value = item.value;
      select.dispatchEvent(new Event("change", { bubbles: true }));
      syncLabel();
      close();
    }

    syncLabel();
    input.addEventListener("focus", function () { input.select(); open(""); });
    input.addEventListener("input", function () { open(input.value); });
    input.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") { e.preventDefault(); if (list.hidden) open(""); else moveActive(list, 1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); moveActive(list, -1); }
      else if (e.key === "Enter") { if (!list.hidden) { e.preventDefault(); pick(activeIndex(list)); } }
      else if (e.key === "Escape") { close(); syncLabel(); }
    });
    list.addEventListener("mousedown", function (e) {
      var opt = e.target.closest(".cbx__opt");
      if (opt) { e.preventDefault(); pick(parseInt(opt.dataset.index, 10)); }
    });
    input.addEventListener("blur", function () { setTimeout(function () { close(); syncLabel(); }, 120); });
  }

  function init(root) {
    (root || document).querySelectorAll("select[data-combobox]").forEach(enhanceSelect);
  }

  window.zetomCombobox = { renderList: renderList, moveActive: moveActive, activeIndex: activeIndex, init: init };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", function () { init(); });
  else init();
})();
