"use strict";
// Presentation only: source-scoped choices and validation also run on the server.
for (const form of document.querySelectorAll("[data-rollout-form]")) {
  const kind = form.querySelector('[name="new_asset_kind"]');
  const group = form.querySelector("[data-rollout-virtualization]");
  if (!kind || !group) continue;
  const virtualization = group.querySelector("select");
  const update = () => {
    const available = kind.value === "vm";
    group.hidden = !available;
    virtualization.disabled = !available;
    if (!available) virtualization.value = "";
  };
  kind.addEventListener("change", update);
  update();
}
