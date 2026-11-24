/* Client helpers. Served from /assets, so it is allowed by script-src 'self'. */
(function () {
  "use strict";

  var pim = {
    // Counter + shortcut hint under the question box
    hint: function (value) {
      var mac = /Mac|iPhone|iPad/.test(navigator.platform || "");
      return (value ? value.length : 0) + "/2000 · " + (mac ? "Cmd" : "Ctrl") + "+Enter to submit";
    },
    // Submit button: disabled when empty or busy; class toggles the spinner label
    submitState: function (value, busy) {
      var empty = !value || !value.trim();
      return [busy || empty, "btn btn-default btn-lg btn-submit" + (busy ? " is-busy" : "")];
    },
    // Per-page document title
    title: function (search) {
      var page = new URLSearchParams(search || "").get("page") || "home";
      var names = {
        home: "", "release-notes": "Release Notes", query: "Query", registry: "Registry",
        statistics: "Statistics", analytics: "Analytics", about: "About", admin: "Admin"
      };
      var name = names[page];
      document.title = name === undefined ? "Page Not Found | PIM AI Global"
        : name ? name + " | PIM AI Global"
        : "PIM AI Global — Public Investment Management Intelligence";
      window.scrollTo(0, 0);
      return window.dash_clientside.no_update;
    }
  };
  window.dash_clientside = Object.assign({}, window.dash_clientside, { pim: pim });

  document.addEventListener("click", function (e) {
    var t = e.target;
    if (!(t instanceof Element)) return;

    var toggle = t.closest(".nav-toggle");
    if (toggle) {
      var nav = document.getElementById("mobile-nav");
      var open = toggle.getAttribute("aria-expanded") !== "true";
      toggle.setAttribute("aria-expanded", String(open));
      toggle.setAttribute("aria-label", open ? "Close navigation menu" : "Open navigation menu");
      if (nav) nav.classList.toggle("is-open", open);
      return;
    }
    if (t.closest("#mobile-nav .nav-link")) {
      var tg = document.querySelector(".nav-toggle");
      if (tg) tg.setAttribute("aria-expanded", "false");
      var mn = document.getElementById("mobile-nav");
      if (mn) mn.classList.remove("is-open");
    }

    var copy = t.closest("[data-copy]");
    if (copy && navigator.clipboard) {
      navigator.clipboard.writeText(copy.getAttribute("data-copy")).then(function () {
        copy.classList.add("is-copied");
        setTimeout(function () { copy.classList.remove("is-copied"); }, 2000);
      });
      return;
    }

    if (t.closest("[data-back]")) {
      e.preventDefault();
      window.history.back();
      return;
    }

    var item = t.closest(".history-item");
    if (item) {
      var d = item.closest("details");
      if (d) d.removeAttribute("open");
    }
  });

  document.addEventListener("keydown", function (e) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && e.target && e.target.id === "q-input") {
      e.preventDefault();
      var btn = document.getElementById("q-submit");
      if (btn && !btn.disabled) btn.click();
    }
  });
})();
