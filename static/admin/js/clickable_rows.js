// claude — clickable changelist rows for Django/Unfold admin.
// Wires each #result_list row to its change-view link so user doesn't
// have to aim for the first column. Ctrl/meta/middle-click open in a
// new tab; clicks on interactive children (checkboxes, actions, inline
// links) are ignored.

(function () {
    "use strict";

    var ROW_SELECTOR = "#result_list tbody tr";
    var IGNORE_SELECTOR = "a, button, input, label, select, textarea, .action-checkbox-column";

    function findChangeLink(row) {
        var links = row.querySelectorAll("a[href]");
        for (var i = 0; i < links.length; i++) {
            var href = links[i].getAttribute("href") || "";
            if (href.indexOf("/change/") !== -1) {
                return links[i];
            }
        }
        return null;
    }

    function decorate() {
        var rows = document.querySelectorAll(ROW_SELECTOR);
        rows.forEach(function (row) {
            if (row.dataset.clickableRow) return;
            var link = findChangeLink(row);
            if (!link) return;
            row.dataset.clickableRow = "1";
            row.dataset.href = link.href;
            row.classList.add("clickable-row");
        });
    }

    function openHref(href, newTab) {
        if (newTab) {
            window.open(href, "_blank", "noopener");
        } else {
            window.location.href = href;
        }
    }

    function onClick(e) {
        var row = e.target.closest(".clickable-row");
        if (!row) return;
        if (e.target.closest(IGNORE_SELECTOR)) return;
        var href = row.dataset.href;
        if (!href) return;
        var newTab = e.ctrlKey || e.metaKey || e.shiftKey;
        if (newTab) e.preventDefault();
        openHref(href, newTab);
    }

    function onAuxClick(e) {
        if (e.button !== 1) return;
        var row = e.target.closest(".clickable-row");
        if (!row) return;
        if (e.target.closest(IGNORE_SELECTOR)) return;
        var href = row.dataset.href;
        if (!href) return;
        e.preventDefault();
        openHref(href, true);
    }

    function init() {
        decorate();
        document.addEventListener("click", onClick);
        document.addEventListener("auxclick", onAuxClick);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
