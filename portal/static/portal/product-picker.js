"use strict";
(() => {
  const root = document.querySelector("[data-product-picker]");
  if (!root) return;
  const form = root.closest("form");
  const vendor = form.elements.vendor;
  const product = form.elements.product_key;
  const query = root.querySelector("#catalog-query");
  const status = root.querySelector("[data-picker-status]");
  const results = root.querySelector("[data-picker-results]");
  const pages = root.querySelector("[data-picker-pages]");
  const installation = root.hasAttribute("data-installation-picker");
  if (installation) {
    form.elements.product_identifier.addEventListener("input", () => { vendor.value = ""; product.value = ""; changed(); });
    form.elements.existing_product.addEventListener("change", () => {
      if (!form.elements.existing_product.value) return;
      vendor.value = ""; product.value = "";
      form.elements.product_name.value = ""; form.elements.product_identifier.value = "";
      changed(); status.textContent = "Saved organization product selected. Enter its installed version below.";
    });
  }
  let generation = 0;
  let controller;
  const clearResults = () => { results.replaceChildren(); pages.replaceChildren(); };
  const changed = () => { generation += 1; if (controller) controller.abort(); clearResults(); status.textContent = ""; };
  vendor.addEventListener("input", changed);
  product.addEventListener("input", changed);
  query.addEventListener("input", changed);
  function apply(vendorKey, productKey, identifier = "") {
    changed();
    vendor.value = vendorKey;
    product.value = productKey;
    if (installation) {
      form.elements.existing_product.value = "";
      form.elements.product_identifier.value = identifier;
      if (productKey) form.elements.product_name.value = productKey;
      status.textContent = productKey ? `Selected ${vendorKey} / ${productKey}. Enter the installed version, then save software to queue monitoring.` : `Manufacturer ${vendorKey} selected. Search its products next.`;
      return;
    }
    status.textContent = productKey ? "Product selected. Save to apply this mapping and start auto-refresh." : "Manufacturer selected. Enter a product search term, then choose Find product.";
  }
  document.querySelectorAll("[data-mapping-vendor]").forEach(button => {
    button.addEventListener("click", () => apply(button.dataset.mappingVendor, button.dataset.mappingProduct));
  });
  async function search(kind, page = 1) {
    changed();
    if (kind === "products" && !vendor.value.trim()) {
      status.textContent = "Choose a manufacturer first, then search its products.";
      return;
    }
    const current = generation;
    const vendorKey = vendor.value;
    const term = query.value;
    controller = new AbortController();
    status.textContent = "Searching the public catalog…";
    try {
      const response = await fetch(root.dataset.searchUrl, {
        method: "POST", credentials: "same-origin", signal: controller.signal,
        headers: {"X-CSRFToken": form.elements.csrfmiddlewaretoken.value},
        body: new URLSearchParams({kind, q: term, vendor: vendorKey, page: String(page)})
      });
      const data = await response.json();
      if (current !== generation) return;
      if (!response.ok) throw new Error(data.error);
      status.textContent = data.results.length ? `${data.total} catalog entries · page ${data.page}/${data.pages}. Choose the exact product identity.` : "No selectable matches. Refine the term or enter the public keys directly.";
      if (data.truncated) status.textContent += " Refine the search to see more than the first 100 pages.";
      data.results.forEach(item => {
        const li = document.createElement("li");
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = `Use ${item.key}`;
        button.addEventListener("click", () => apply(kind === "vendors" ? item.key : vendorKey, kind === "vendors" ? "" : item.key, item.identifier || ""));
        li.append(button); results.append(li);
      });
      [["Previous", data.page - 1], ["Next", data.page + 1]].forEach(([label, target]) => {
        if (target < 1 || target > data.pages) return;
        const button = document.createElement("button"); button.type = "button";
        button.textContent = label; button.addEventListener("click", () => search(kind, target)); pages.append(button);
      });
    } catch (error) {
      if (current !== generation || error.name === "AbortError") return;
      status.textContent = "Product catalog unavailable. Your entered values are retained; retry or enter the keys directly.";
    }
  }
  root.querySelectorAll("[data-search]").forEach(button => button.addEventListener("click", () => search(button.dataset.search)));
  query.addEventListener("keydown", event => { if (event.key === "Enter") { event.preventDefault(); search(vendor.value.trim() ? "products" : "vendors"); } });
})();
