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
  const date = value => value ? new Date(value).toLocaleString() : null;
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
    text(node.querySelector("[data-lookup-attempt]"), date(row.last_attempt) || "Not yet attempted");
    text(node.querySelector("[data-lookup-success]"), date(row.last_success) || "None yet");
    text(node.querySelector("[data-lookup-updated]"), date(observed));
    const details = node.querySelector("[data-lookup-errors]");
    details.hidden = !row.errors.length;
    const signature = JSON.stringify(row.errors);
    if (details.dataset.signature !== signature) {
      details.querySelector("ul").replaceChildren(...row.errors.map(error => {
        const li = document.createElement("li"); li.textContent = `${error.count} · ${error.reason}`; return li;
      }));
      details.dataset.signature = signature;
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
