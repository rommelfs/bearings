"use strict";
(() => {
  const search = document.querySelector("[data-search]");
  if (search) {
    search.hidden = false;
    const field = document.querySelector("#faq-search");
    const items = [...document.querySelectorAll(".faq-item")];
    const count = document.querySelector("#faq-count");
    const update = () => {
      const words = field.value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
      let visible = 0;
      for (const item of items) {
        item.hidden = !words.every(word => item.textContent.toLocaleLowerCase().includes(word));
        if (!item.hidden) visible++;
      }
      count.textContent = `${visible} / ${items.length} ${count.dataset.label}`;
      document.querySelector("#faq-empty").hidden = visible !== 0;
    };
    field.addEventListener("input", update);
    update();
  }
  const dialog = document.querySelector("#image-dialog");
  if (!dialog || typeof dialog.showModal !== "function") return;
  document.querySelectorAll("[data-lightbox]").forEach(link => {
    link.addEventListener("click", event => {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      const image = dialog.querySelector("img");
      image.src = link.href;
      image.alt = link.querySelector("img").alt;
      dialog.showModal();
    });
  });
  dialog.querySelector("[data-close]").addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", event => { if (event.target === dialog) dialog.close(); });
})();
