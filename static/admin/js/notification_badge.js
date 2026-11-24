// claude — live unread-count для admin-шапки.
// Polls /notifications/unread-count/ и обновляет:
//   1) <title> вкладки: префикс "(N) " когда N > 0
//   2) все ссылки на /notifications/ (sidebar Inbox + ACCOUNT dropdown) —
//      добавляет/обновляет pill-бейдж .js-unread-badge.
// При 401/302/HTML-ответе (сессия истекла) polling останавливается, чтобы не
// долбить логин-страницу.

(function () {
    "use strict";

    var ENDPOINT = "/notifications/unread-count/";
    var POLL_MS = 30000;
    var INBOX_HREFS = ["/notifications/", "/notifications"];

    var pollTimer = null;
    var baseTitle = document.title.replace(/^\(\d+\)\s*/, "");

    function setTabTitle(count) {
        document.title = count > 0 ? "(" + count + ") " + baseTitle : baseTitle;
    }

    function isInboxLink(a) {
        var href = a.getAttribute("href") || "";
        // Точное совпадение, чтобы не зацепить /notifications/1/read/ и т.п.
        return INBOX_HREFS.indexOf(href) !== -1;
    }

    function setBadgeOnLink(link, count) {
        var badge = link.querySelector(".js-unread-badge");
        if (count <= 0) {
            if (badge) badge.remove();
            return;
        }
        if (!badge) {
            badge = document.createElement("span");
            badge.className = "js-unread-badge";
            link.appendChild(badge);
        }
        badge.textContent = String(count);
    }

    function updateBadges(count) {
        var links = document.querySelectorAll("a[href]");
        for (var i = 0; i < links.length; i++) {
            if (isInboxLink(links[i])) {
                setBadgeOnLink(links[i], count);
            }
        }
    }

    function stop() {
        if (pollTimer !== null) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
    }

    function poll() {
        fetch(ENDPOINT, {
            credentials: "same-origin",
            headers: {Accept: "application/json"},
            redirect: "manual",
        }).then(function (res) {
            // Сессия истекла / редирект на логин — гасим polling.
            if (res.type === "opaqueredirect" || !res.ok) {
                stop();
                return null;
            }
            var ct = res.headers.get("Content-Type") || "";
            if (ct.indexOf("application/json") === -1) {
                stop();
                return null;
            }
            return res.json();
        }).then(function (data) {
            if (!data) return;
            var count = parseInt(data.count, 10) || 0;
            setTabTitle(count);
            updateBadges(count);
        }).catch(function () {
            // Сетевой сбой — оставляем предыдущее состояние, следующий tick попробует снова.
        });
    }

    function init() {
        poll();
        pollTimer = setInterval(poll, POLL_MS);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
