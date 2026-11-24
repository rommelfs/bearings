"use strict";
(() => {
  const widgets = [...document.querySelectorAll("[data-ubuntu-progress]")];
  if (!widgets.length) return;
  const globalRefresh = document.querySelector("[data-overview-refresh]");
  const interval = 10000;
  let busy = false, timer, failures = 0;
  const counts = ["total", "fresh", "pending", "failed", "refresh_errors"];
  const text = (node, value) => { if (node && node.textContent !== String(value)) node.textContent = String(value); };
  const status = (node, value) => {
    const target = node.querySelector("[data-lookup-status]");
    target.classList.toggle("warning", value.startsWith("Unable") || value.startsWith("Offline"));
    text(target, value);
  };
  const automatic = node => node.querySelector("[data-lookup-auto]").checked && (!globalRefresh || globalRefresh.checked);
  const date = (value, node) => {
    if (!value) return null;
    const parts = new Intl.DateTimeFormat("en-GB", {year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23", timeZone: node.dataset.timezone || "Europe/Berlin", timeZoneName: "short"}).formatToParts(new Date(value));
    const p = Object.fromEntries(parts.map(part => [part.type, part.value]));
    return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}:${p.second} ${p.timeZoneName}`;
  };
  const panelRequests = new Map();
  async function refreshPanel(node, evaluation, target) {
    const panel = [...document.querySelectorAll("[data-evaluation-panel]")].find(el => el.dataset.device === node.dataset.device);
    if (!panel || panel.dataset.revision === evaluation.revision || panelRequests.has(node.dataset.device)) return;
    const message = node.querySelector("[data-evaluation-render-status]");
    if (panel.contains(document.activeElement)) { text(message, "New assessment available; leave this assessment's current control to display it."); return; }
    const url = new URL(target, location.href);
    if (url.origin !== location.origin) return;
    const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 8000);
    panelRequests.set(node.dataset.device, controller);
    try {
      const response = await fetch(url, {credentials: "same-origin", cache: "no-store", redirect: "error", signal: controller.signal, headers: {Accept: "application/json"}});
      if (!response.ok || !response.headers.get("Content-Type")?.includes("application/json")) throw new Error("response");
      const data = await response.json();
      if (data.schema !== "bearings.evaluation-panel.v1" || typeof data.revision !== "string" || !/^[a-f0-9]{64}$/.test(data.revision) || typeof data.html !== "string" || data.html.length > 250000) throw new Error("shape");
      if (panel.contains(document.activeElement)) { text(message, "New assessment available; leave this assessment's current control to display it."); return; }
      const doc = new DOMParser().parseFromString(data.html, "text/html"), next = doc.querySelector("[data-evaluation-panel]");
      if (!next || next.dataset.device !== node.dataset.device || next.dataset.revision !== data.revision) throw new Error("panel");
      next.querySelectorAll("script,iframe,object,embed,style,link").forEach(el => el.remove());
      [next, ...next.querySelectorAll("*")].forEach(el => [...el.attributes].forEach(attr => { if (/^on/i.test(attr.name) || attr.name === "srcdoc") el.removeAttribute(attr.name); }));
      const opened = new Set([...panel.querySelectorAll("details[open][data-eval-disclosure]")].map(el => el.dataset.evalDisclosure));
      next.querySelectorAll("details[data-eval-disclosure]").forEach(el => { el.open = opened.has(el.dataset.evalDisclosure); });
      const top = scrollY, left = scrollX;
      panel.replaceWith(next); window.scrollTo(left, top);
      if (data.evaluation && typeof data.evaluation.message === "string" && data.evaluation.message.length <= 500) {
        text(node.querySelector("[data-evaluation-phase]"), data.evaluation.message);
        node.querySelector("[data-evaluation-phase]")?.classList.toggle("warning", Boolean(data.evaluation.historical));
      }
      text(message, "Package assessment refreshed from the latest evaluation snapshot.");
    } catch (_) { text(message, "Assessment refresh unavailable; the dated previous assessment is retained."); }
    finally { clearTimeout(timeout); panelRequests.delete(node.dataset.device); }
  }
  function valid(row) {
    return row && counts.every(key => Number.isSafeInteger(row[key]) && row[key] >= 0 && row[key] <= 1000000)
      && row.fresh + row.pending + row.failed === row.total && row.refresh_errors <= row.fresh
      && [row.last_attempt, row.last_success].every(value => value == null || (typeof value === "string" && Number.isFinite(Date.parse(value))))
      && Array.isArray(row.errors) && row.errors.length <= 64
      && row.errors.every(error => Number.isSafeInteger(error.count) && error.count >= 0 && error.count <= row.total && typeof error.reason === "string" && error.reason.length <= 160);
  }
  function update(node, row, observed) {
    counts.forEach(key => text(node.querySelector(`[data-count="${key}"]`), row[key]));
    const bar = node.querySelector("[data-lookup-bar]");
    bar.max = Math.max(1, row.total); bar.value = row.fresh;
    text(node.querySelector("[data-lookup-percent]"), row.total ? Math.round(100 * row.fresh / row.total) : 0);
    node.querySelector("[data-lookup-empty]").hidden = row.total > 0;
    node.querySelector("[data-refresh-warning]").hidden = !row.refresh_errors;
    text(node.querySelector("[data-lookup-attempt]"), date(row.last_attempt, node) || "Not yet attempted");
    text(node.querySelector("[data-lookup-success]"), date(row.last_success, node) || "None yet");
    text(node.querySelector("[data-lookup-updated]"), date(observed, node));
    const details = node.querySelector("[data-lookup-errors]");
    details.hidden = !row.errors.length;
    const signature = JSON.stringify(row.errors);
    if (details.dataset.signature !== signature) {
      details.querySelector("ul").replaceChildren(...row.errors.map(error => {
        const li = document.createElement("li"); li.textContent = `${error.count} · ${error.reason}`; return li;
      }));
      details.dataset.signature = signature;
    }
    if (row.evaluation && typeof row.evaluation.message === "string" && row.evaluation.message.length <= 500 && /^[a-f0-9]{64}$/.test(row.evaluation.revision)) {
      text(node.querySelector("[data-evaluation-phase]"), row.evaluation.message);
      node.querySelector("[data-evaluation-phase]")?.classList.toggle("warning", Boolean(row.evaluation.historical));
      if (typeof row.evaluation_url === "string") refreshPanel(node, row.evaluation, row.evaluation_url);
    }
    status(node, automatic(node) ? "Counters update automatically; the page stays in place." : "Automatic updates paused; last retrieved counters shown.");
  }
  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(() => refresh(), Math.min(60000, interval * 2 ** Math.min(failures, 3)));
  }
  async function refresh(forced) {
    if (busy) return;
    clearTimeout(timer);
    if (document.visibilityState !== "visible" || !navigator.onLine) {
      widgets.forEach(node => status(node, navigator.onLine ? "Paused while this tab is hidden." : "Offline; last retrieved counters retained."));
      schedule(); return;
    }
    const selected = widgets.filter(node => automatic(node) || node === forced);
    if (!selected.length) { schedule(); return; }
    busy = true;
    try {
      const endpoint = new URL(selected[0].dataset.endpoint, location.href);
      if (endpoint.origin !== location.origin || selected.some(node => node.dataset.endpoint !== selected[0].dataset.endpoint)) throw new Error("endpoint");
      const ids = [...new Set(selected.map(node => node.dataset.device))];
      for (let offset = 0; offset < ids.length; offset += 36) {
        const batch = ids.slice(offset, offset + 36), url = new URL(endpoint);
        batch.forEach(id => url.searchParams.append("device", id));
        const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 8000);
        try {
          const response = await fetch(url, {credentials: "same-origin", cache: "no-store", redirect: "error", signal: controller.signal, headers: {Accept: "application/json"}});
          if (!response.ok || !response.headers.get("Content-Type")?.includes("application/json")) throw new Error("response");
          const data = await response.json();
          if (data.schema !== "bearings.lookup-progress.v1" || typeof data.observed_at !== "string" || !Number.isFinite(Date.parse(data.observed_at)) || !data.devices || !batch.every(id => valid(data.devices[id]))) throw new Error("shape");
          selected.filter(node => batch.includes(node.dataset.device)).forEach(node => update(node, data.devices[node.dataset.device], data.observed_at));
        } finally { clearTimeout(timeout); }
      }
      failures = 0;
    } catch (_) {
      failures += 1;
      selected.forEach(node => status(node, "Unable to refresh; last retrieved counters retained. Retrying automatically or choose Refresh now."));
    } finally { busy = false; schedule(); }
  }
  function choice() {
    widgets.forEach(node => status(node, automatic(node) ? "Automatic counter updates enabled." : "Automatic updates paused; last retrieved counters shown."));
    refresh();
  }
  widgets.forEach(node => {
    node.querySelector("[data-lookup-auto]").addEventListener("change", choice);
    node.querySelector("[data-lookup-now]").addEventListener("click", () => refresh(node));
  });
  globalRefresh?.addEventListener("change", choice);
  document.addEventListener("visibilitychange", () => refresh());
  window.addEventListener("online", () => refresh());
  window.addEventListener("offline", () => refresh());
  refresh();
})();
