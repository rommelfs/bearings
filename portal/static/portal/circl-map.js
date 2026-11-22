// Vitrine map; all organization/evidence policy and local geocoding stay server-side.
let rendererReady = true;
try {
  await import("./vitrine-widgets.js");
} catch {
  rendererReady = false;
}
const colors = {
  critical: "#b91446",
  high: "#c65316",
  medium: "#bf8a00",
  low: "#287fb0",
  unrated: "#775da2",
  no_open: "#647880",
};
const names = {
  critical: "Critical",
  high: "High",
  medium: "Medium / Review",
  low: "Low",
  unrated: "Unrated / informational",
  no_open: "No open problems recorded",
};
function element(tag, text) {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text;
  return e;
}
function link(text, url) {
  const a = element("a", text);
  try {
    const u = new URL(url, location.href);
    if (u.origin === location.origin && /^https?:$/.test(u.protocol))
      a.href = u.href;
  } catch {}
  return a;
}
for (const map of document.querySelectorAll("vt-map"))
  map.addEventListener("bearings-tile-state", (event) => {
    const note = map.parentElement.querySelector("[data-tile-status]");
    if (note)
      note.textContent =
        event.detail.state === "unavailable"
          ? "CIRCL background unavailable; local country shapes remain usable."
          : "";
  });
const editor = document.querySelector("[data-location-editor]");
if (editor && rendererReady) {
  const lat = document.querySelector("#id_latitude"),
    lon = document.querySelector("#id_longitude");
  function position(fit = false) {
    const a = Number(lat.value),
      o = Number(lon.value);
    if (
      !lat.value.trim() ||
      !lon.value.trim() ||
      !Number.isFinite(a) ||
      !Number.isFinite(o) ||
      Math.abs(a) > 90 ||
      Math.abs(o) > 180
    )
      return;
    editor.pins = [];
    editor.content = JSON.stringify({
      markers: [
        { lat: a, lon: o, label: "Selected company point", color: "#18716d" },
      ],
    });
    if (fit) editor.setView(a, o, 700);
  }
  editor.addEventListener("vt-select", (event) => {
    if (event.detail.type !== "point") return;
    lat.value = event.detail.lat.toFixed(6);
    lon.value = event.detail.lon.toFixed(6);
    position();
  });
  lat.addEventListener("change", () => position(true));
  lon.addEventListener("change", () => position(true));
  position(true);
}
const root = document.querySelector("[data-company-map]");
if (root) {
  const map = root.querySelector("vt-map"),
    status = root.querySelector("[data-map-status]"),
    stats = root.querySelector("vt-stats"),
    selected = root.querySelector("[data-map-selection]");
  let payload = null,
    page = 0,
    controller,
    groups = new Map(),
    fitPending = false;
  const table = root.querySelector("[data-map-table]"),
    unlocated = root.querySelector("[data-map-unlocated]");
  function companyContent(point) {
    const box = element("div");
    box.append(
      link(point.name, point.company_url),
      element("p", names[point.level]),
    );
    const problems = element("p");
    if (point.reviews)
      problems.append(
        link(point.reviews + " outstanding CVE reviews", point.reviews_url),
      );
    if (point.reviews && point.issues) problems.append(element("br"));
    if (point.issues)
      problems.append(
        link(point.issues + " other outstanding issues", point.issues_url),
      );
    if (!point.reviews && !point.issues)
      problems.append(
        element(
          "span",
          "No open problems recorded; coverage may be incomplete.",
        ),
      );
    box.append(problems, element("p", point.label));
    if (point.location_url)
      box.append(
        link("Position / correct company point →", point.location_url),
      );
    return box;
  }
  function matching() {
    if (!payload) return [];
    const level = root.querySelector("[data-map-level]").value;
    const query = root
      .querySelector("[data-map-search]")
      .value.toLocaleLowerCase();
    return payload.points.filter(
      (p) =>
        (level === "all" || p.level === level) &&
        p.name.toLocaleLowerCase().includes(query),
    );
  }
  function renderTable(points) {
    table.replaceChildren();
    const pages = Math.max(1, Math.ceil(points.length / 50));
    page = Math.min(page, pages - 1);
    points.slice(page * 50, page * 50 + 50).forEach((p) => {
      const tr = element("tr"),
        company = element("td"),
        problems = element("td");
      company.append(link(p.name, p.company_url));
      const content = companyContent(p);
      problems.append(content.children[2]);
      tr.append(
        company,
        element("td", p.label),
        element("td", names[p.level]),
        problems,
      );
      table.append(tr);
    });
    if (!points.length) {
      const tr = element("tr"),
        td = element(
          "td",
          "No located companies match. Check unlocated companies below.",
        );
      td.colSpan = 4;
      tr.append(td);
      table.append(tr);
    }
    root.querySelector("[data-map-page]").textContent =
      `Page ${page + 1} / ${pages} · ${points.length} companies`;
    root.querySelector("[data-map-previous]").disabled = page === 0;
    root.querySelector("[data-map-next]").disabled = page >= pages - 1;
  }

  function draw(fit = false) {
    if (!payload) return;
    const points = matching();
    groups = new Map();
    for (const p of points) {
      const key = p.lat.toFixed(4) + "," + p.lon.toFixed(4);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(p);
    }
    selected.replaceChildren();
    const markers = [...groups.values()].map((group) => {
      const worst = group.reduce((a, b) => (a.rank >= b.rank ? a : b));
      return {
        lat: worst.lat,
        lon: worst.lon,
        label:
          group.length === 1
            ? worst.name
            : `${group.length} companies · ${names[worst.level]}`,
        color: colors[worst.level],
      };
    });
    map.heatPoints =
      root.querySelector("[data-map-mode]").value === "heat"
        ? points
            .filter((p) => p.rank > 0)
            .map((p) => ({
              ...p,
              weight: Math.min(20, p.reviews + p.issues) * p.rank,
            }))
        : [];
    fitPending = fit;
    map.content = JSON.stringify({ markers });
    if (rendererReady) map.update();
    if (fit && map.projection) {
      fitPending = false;
      map.fitPoints(points);
    }
    const s = payload.summary;
    stats.content = JSON.stringify([
      { label: "Permitted companies", value: s.companies },
      { label: "Located companies", value: s.located },
      { label: "Location missing", value: s.unlocated },
      { label: "Shown after filters", value: points.length },
    ]);
    status.textContent = `${s.shown} of ${s.located} located ${s.located === 1 ? "company" : "companies"} loaded · ${s.unlocated} unlocated (${s.missing_address} without an address; ${s.unlocated_with_problems} with open problems) · ${s.companies} permitted ${s.companies === 1 ? "company" : "companies"}. ${points.length} ${points.length === 1 ? "company matches" : "companies match"} the filters.`;
    if (s.omitted)
      status.textContent += ` Limit ${payload.limit}: ${s.omitted} additional located companies are not shown.`;
    if (s.stale_manual)
      status.textContent += ` ${s.stale_manual} manual points invalidated by address changes; local lookup is used where available.`;
    if (!rendererReady)
      status.textContent += " Map renderer unavailable; use the company table.";
    renderTable(points);
  }
  map.addEventListener("bearings-map-ready", () => {
    if (fitPending) {
      fitPending = false;
      map.fitPoints(matching());
    }
  });
  map.addEventListener("vt-select", (event) => {
    if (event.detail.type !== "point") return;
    const key = event.detail.lat.toFixed(4) + "," + event.detail.lon.toFixed(4),
      group = groups.get(key);
    if (!group) return;
    selected.replaceChildren(
      element(
        "h3",
        group.length === 1
          ? "Selected company"
          : `${group.length} companies at this approximate point`,
      ),
    );
    for (const p of group.slice(0, 30)) selected.append(companyContent(p));
    if (group.length > 30)
      selected.append(
        element(
          "p",
          "First 30 shown; use the searchable company table for all loaded companies.",
        ),
      );
  });
  async function load() {
    if (controller) controller.abort();
    controller = new AbortController();
    const active = controller;
    map.content = "";
    map.heatPoints = [];
    if (rendererReady) map.update();
    groups.clear();
    selected.replaceChildren();
    stats.content = "[]";
    payload = null;
    table.replaceChildren();
    unlocated.replaceChildren();
    status.textContent = "Loading current permitted company locations…";
    root.querySelector("[data-map-page]").textContent = "";
    root.querySelector("[data-map-previous]").disabled = true;
    root.querySelector("[data-map-next]").disabled = true;
    const timer = setTimeout(() => active.abort(), 15000);
    try {
      const response = await fetch(root.dataset.url, {
        credentials: "same-origin",
        cache: "no-store",
        signal: active.signal,
      });
      if (!response.ok || response.redirected) throw Error();
      const data = await response.json();
      if (active !== controller) return;
      payload = data;
      payload.unlocated.forEach((p) => {
        const li = element("li");
        li.append(
          link(p.name, p.company_url),
          " · " + names[p.level] + " · " + (p.reviews + p.issues) + " open",
        );
        if (p.location_url)
          li.append(" · ", link("Set company point", p.location_url));
        unlocated.append(li);
      });
      if (!payload.unlocated.length)
        unlocated.append(element("li", "No unlocated companies."));
      draw(true);
    } catch (error) {
      if (active === controller)
        status.textContent =
          "Map data unavailable. Check your session and retry Refresh map; company/problem lists remain available.";
    } finally {
      clearTimeout(timer);
    }
  }
  root.querySelector("[data-map-reload]").addEventListener("click", load);
  root
    .querySelector("[data-map-fit]")
    .addEventListener("click", () => draw(true));
  root
    .querySelector("[data-map-mode]")
    .addEventListener("change", () => draw());
  root.querySelector("[data-map-level]").addEventListener("change", () => {
    page = 0;
    draw();
  });
  root.querySelector("[data-map-search]").addEventListener("input", () => {
    page = 0;
    draw();
  });
  root.querySelector("[data-map-previous]").addEventListener("click", () => {
    page--;
    renderTable(matching());
  });
  root.querySelector("[data-map-next]").addEventListener("click", () => {
    page++;
    renderTable(matching());
  });
  load();
}
