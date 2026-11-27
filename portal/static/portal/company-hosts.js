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
    status.textContent = "Loading CVE assessment…";
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    let failure = "CVE assessment could not load.";
    try {
      const response = await fetch(panel.dataset.hostPanel, {
        credentials: "same-origin", cache: "no-store", signal: controller.signal,
      });
      if (response.redirected) {
        failure = "CVE assessment was redirected. Reload this page to check your session.";
        throw new Error("Unexpected redirect");
      }
      if (!response.ok) {
        const reason = response.headers.get("X-Bearings-Host-Error");
        if (reason === "request_budget" || reason === "query_cancelled") {
          failure = `CVE assessment exceeded the server time limit (HTTP ${response.status}).`;
        } else if (reason === "database") {
          failure = `CVE assessment encountered a database error (HTTP ${response.status}).`;
        } else {
          failure = `CVE assessment could not load (HTTP ${response.status}).`;
        }
        throw new Error("Unsuccessful assessment response");
      }
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
      if (controller.signal.aborted) failure = "CVE assessment took too long.";
      status.textContent = failure;
      loadLink.textContent = "Retry CVE assessment →";
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
