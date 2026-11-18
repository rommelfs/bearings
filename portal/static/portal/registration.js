"use strict";
(() => {
  const token = new URLSearchParams(window.location.hash.slice(1)).get("token");
  const field = document.querySelector("#id_code, #token");
  if (field && token && /^[A-Za-z0-9_-]{43}$/.test(token)) field.value = token;
  if (window.location.hash) history.replaceState(null, "", window.location.pathname + window.location.search);
})();
