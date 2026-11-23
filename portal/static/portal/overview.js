"use strict";
(() => {
  const refresh = document.querySelector("[data-overview-refresh]");
  if (!refresh) return;
  if (document.querySelector("[data-ubuntu-progress]")) {
    const label = document.querySelector("[data-overview-refresh-label]");
    if (label) label.textContent = "Refresh lookup counters every 10 seconds (other totals: reload page)";
    return;
  }
  setInterval(() => {
    const active = document.activeElement;
    if (refresh.checked && document.visibilityState === "visible" && (!active || !active.matches("input:not([type=checkbox]),select,textarea"))) window.location.reload();
  }, 60000);
})();
