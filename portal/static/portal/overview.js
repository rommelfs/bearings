"use strict";
(() => {
  const refresh = document.querySelector("[data-overview-refresh]");
  if (!refresh) return;
  setInterval(() => {
    const active = document.activeElement;
    if (refresh.checked && document.visibilityState === "visible" && (!active || !active.matches("input:not([type=checkbox]),select,textarea"))) window.location.reload();
  }, 60000);
})();
