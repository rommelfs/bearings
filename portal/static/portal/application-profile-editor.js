"use strict";
(() => {
  const form = document.querySelector("[data-application-profile-editor]");
  if (!form) return;
  const show = (name, visible) => { const row = form.elements[name]?.closest("p"); if (row) row.hidden = !visible; };
  const update = () => {
    const method = form.elements.method.value;
    const generic = method !== "misp-version-json";
    const pathLabel = form.querySelector('label[for="id_path"]');
    if (pathLabel) pathLabel.textContent = method === "git-tag" ? "Git repository directory on the monitored host:" : "Version metadata file on the monitored host:";
    ["name", "identifier", "version_pattern"].forEach(name => show(name, generic));
    show("json_fields", method === "json-fields");
    const messages = {
      "misp-version-json": "Reads only MISP's integer major/minor/hotfix release file. No PHP or Git execution.",
      "json-fields": "Extract scalar JSON fields, then normalize exactly one release version. No JSONPath code or application execution.",
      "file-regex": "Match exactly one version using Go/RE2. Select non-secret release metadata; the file is read, never executed.",
      "git-tag": "Use tags pointing at HEAD and a tracked-clean status. A commit hash, dirty tree or ancestor tag does not become a release version."
    };
    form.querySelector("[data-method-help]").textContent = messages[method];
  };
  form.elements.method.addEventListener("change", update);
  update();
})();
