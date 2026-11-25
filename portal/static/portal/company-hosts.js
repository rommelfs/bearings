"use strict";
(() => {
  function revealSection() {
    const hash = window.location.hash;
    if (!["#inventory", "#contacts", "#scope", "#findings", "#organization-administration"].includes(hash)) return;
    const target = document.getElementById(hash.slice(1));
    const details = target?.closest("details.organization-administration");
    if (details && !details.open) {
      details.open = true;
      target.scrollIntoView();
    }
  }

  revealSection();
  window.addEventListener("hashchange", revealSection);

  const panel = document.querySelector("[data-host-panel]");
  if (!panel) return;
  const loadLink = panel.querySelector("[data-load-hosts]");
  const status = panel.querySelector("[data-host-load-status]");
  async function load() {
    if (!panel.isConnected || panel.getAttribute("aria-busy") === "true") return;
    panel.setAttribute("aria-busy", "true");
    status.textContent = "Loading host overview…";
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(panel.dataset.hostPanel, {
        credentials: "same-origin", cache: "no-store", signal: controller.signal,
      });
      if (response.redirected || !response.ok) throw new Error("Host overview unavailable");
      const html = document.createElement("template");
      html.innerHTML = await response.text();
      const hosts = html.content.querySelector("#hosts");
      if (!hosts) throw new Error("Host overview unavailable");
      const focusWasOnLoadLink = document.activeElement === loadLink;
      panel.replaceWith(hosts);
      if (focusWasOnLoadLink) {
        const heading = hosts.querySelector("#host-heading");
        heading.tabIndex = -1;
        heading.focus();
      }
    } catch {
      status.textContent = "Host overview temporarily unavailable. Select Load host overview to retry.";
    } finally {
      clearTimeout(timeout);
      panel.removeAttribute("aria-busy");
    }
  }

  loadLink.addEventListener("click", (event) => {
    if (event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
    event.preventDefault();
    load();
  });
  window.addEventListener("hashchange", () => {
    if (window.location.hash === "#hosts") load();
  });
  if (!window.location.hash || window.location.hash === "#hosts") load();
})();
