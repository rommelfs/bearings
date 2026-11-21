(() => {
  "use strict";
  const form = document.querySelector("[data-configuration-form]");
  if (!form) return;
  const status = document.querySelector("[data-save-status]");
  const errors = document.querySelector("[data-save-errors]");
  let timer, dirty = false, sequence = 0, chain = Promise.resolve(), conflict = false;
  function save(action = "save") {
    chain = chain.then(async () => {
      if (conflict) return false;
      if (!dirty && action === "save") return true;
      const sent = sequence;
      const data = new FormData(form);
      data.set("action", action);
      status.textContent = "Saving…";
      try {
        const response = await fetch(form.getAttribute("action") || window.location.href, {method: "POST", body: data, headers: {Accept: "application/json"}, credentials: "same-origin"});
        if (response.status === 409) {
          conflict = true;
          throw new Error("Changed in another tab or editor. Your text is still here; copy it before reloading and reconciling.");
        }
        if (!response.ok) throw new Error("Not saved. Check your connection and access, then choose Save now.");
        const result = await response.json();
        form.elements.revision.value = result.revision;
        form.elements.baseline.value = result.baseline;
        dirty = sent !== sequence;
        status.textContent = dirty ? "Unsaved changes…" : result.message;
        errors.replaceChildren();
        for (const [name, items] of Object.entries(result.errors)) {
          for (const item of items) {
            const p = document.createElement("p");
            p.textContent = (name === "__all__" ? "" : `${name.replaceAll("_", " ")}: `) + item.message;
            errors.append(p);
          }
        }
        if (result.unsaved_fields.length) dirty = true;
        document.querySelector("[data-setup-progress]").value = result.progress.percent;
        document.querySelector("[data-setup-count]").textContent = `${result.progress.done} / ${result.progress.total} sections reviewed`;
        document.querySelector("[data-setup-percent]").textContent = `${result.progress.percent}%`;
        document.querySelector("[data-setup-celebration]").hidden = result.progress.percent !== 100;
        for (const item of result.progress.items) {
          const check = document.querySelector(`[data-setup-check="${item.key}"]`);
          if (check) check.hidden = !item.complete;
        }
        if (result.restart_inventory && !dirty) location.reload();
        if (action === "complete" && result.valid && !dirty) {
          const next = document.querySelector("[data-setup-next]");
          if (form.dataset.guided === "true") location.assign(next.href);
        }
        return !dirty;
      } catch (error) {
        dirty = true;
        status.textContent = error.message || "Not saved. Choose Save now to retry.";
        return false;
      }
    });
    return chain;
  }
  form.addEventListener("input", () => {
    dirty = true;
    sequence += 1;
    status.textContent = "Unsaved changes…";
    clearTimeout(timer);
    timer = setTimeout(() => save(), 900);
  });
  form.addEventListener("change", () => {
    dirty = true; sequence += 1; clearTimeout(timer); save();
  });
  form.addEventListener("submit", async event => {
    event.preventDefault(); clearTimeout(timer);
    dirty = true;
    await save(event.submitter?.value || "save");
  });
  document.addEventListener("click", async event => {
    const link = event.target.closest("a[href]");
    if (!link || event.ctrlKey || event.metaKey || event.shiftKey || link.target === "_blank" || !dirty) return;
    event.preventDefault(); clearTimeout(timer);
    if (await save()) location.assign(link.href);
  });
  document.addEventListener("submit", async event => {
    if (event.target === form || !dirty) return;
    event.preventDefault(); clearTimeout(timer);
    if (await save()) event.target.submit();
  });
  window.addEventListener("beforeunload", event => {
    if (dirty) { event.preventDefault(); event.returnValue = ""; }
  });
})();
