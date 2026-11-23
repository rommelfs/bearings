"use strict";
(() => {
  const form = document.querySelector("#research-form");
  const mode = form?.querySelector('[name="mode"]');
  if (!mode) return;
  function update() {
    for (const [name, active] of [["version", mode.value === "exact"], ["minimum", mode.value === "range"], ["maximum", mode.value === "range"]]) {
      const row = form.querySelector(`[data-research-field="${name}"]`);
      if (row) row.hidden = !active;
      // Keep entered values when switching rules; server validation remains authoritative.
    }
  }
  mode.addEventListener("change", update);
  update();
})();
