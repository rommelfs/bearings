// Pinned Vitrine components, served locally. Content is assigned as text only.
import {
  VtMap,
  VtStats,
  VtCode,
  VtChart,
  configure,
} from "./vendor/vitrine/vitrine.js";
configure({
  theme: "light",
  lang: "en",
  vendorUrl: new URL("./vendor/vitrine/", import.meta.url).href,
  maxSize: 2_000_000,
});
const SVG = "http://www.w3.org/2000/svg";
const svg = (name, attrs = {}) => {
  const e = document.createElementNS(SVG, name);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
  return e;
};
const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
const wrap = (x) => ((((x + 180) % 360) + 360) % 360) - 180;
// Regional XYZ/heat adapter for Vitrine 0.14's SVG map. Upstream files stay unchanged.
export class BearingsMap extends VtMap {
  initialView() {
    const v = super.initialView();
    const z = Number(this.getAttribute("zoom"));
    if (Number.isFinite(z) && z > 0) v.zoom = clamp(z, 1, 32768);
    return v;
  }
  zoomBy(factor, around) {
    const v = (this.viewState ??= this.initialView()),
      z = clamp(v.zoom * factor, 1, 32768);
    if (around && this.projection) {
      const at = this.projection.invert(around);
      if (at && at.every(Number.isFinite)) {
        const share = 1 - v.zoom / z;
        v.lon = wrap(v.lon + wrap(at[0] - v.lon) * share);
        v.lat = clamp(v.lat + (at[1] - v.lat) * share, -85, 85);
      }
    }
    v.zoom = z;
    this.scheduleUpdate();
    this.changedSoon();
  }
  clickAt(event) {
    // Pointer capture retargets clicks to the SVG; resolve nearby pins explicitly.
    if (!this.flag("pick", false) && this.projection) {
      const xy = this.pointOf(event),
        markers = JSON.parse(this.content || "{}").markers || [];
      let nearest = null,
        distance = 18;
      for (const marker of markers) {
        const at = this.projection([marker.lon, marker.lat]);
        if (!at) continue;
        const d = Math.hypot(at[0] - xy[0], at[1] - 10 - xy[1]);
        if (d < distance) {
          nearest = marker;
          distance = d;
        }
      }
      if (nearest) {
        this.selectPoint(nearest, nearest.label);
        return;
      }
    }
    super.clickAt(event);
  }
  setView(lat, lon, zoom = 250) {
    this.viewState = {
      lat: clamp(lat, -85, 85),
      lon: wrap(lon),
      zoom: clamp(zoom, 1, 32768),
    };
    this.update();
    this.changedSoon();
  }
  fitPoints(points) {
    if (!this.projection || !points.length) return;
    const lats = points.map((p) => p.lat),
      lons = points.map((p) => p.lon),
      lat = (Math.min(...lats) + Math.max(...lats)) / 2,
      lon = (Math.min(...lons) + Math.max(...lons)) / 2;
    const my = (a) =>
      Math.log(Math.tan(Math.PI / 4 + (clamp(a, -85, 85) * Math.PI) / 360)) /
      (2 * Math.PI);
    const dx = Math.max((Math.max(...lons) - Math.min(...lons)) / 360, 0.0004),
      dy = Math.max(my(Math.max(...lats)) - my(Math.min(...lats)), 0.0004);
    const base = (2 * Math.PI * this.projection.scale()) / this.view.zoom;
    this.setView(lat, lon, Math.min(960 / (dx * 1.3), 540 / (dy * 1.3)) / base);
  }
  build(geo) {
    super.build(geo);
    this.dispatchEvent(new CustomEvent("bearings-map-ready"));
  }
  update() {
    super.update();
    if (!this.svgEl || !this.projection) return;
    this.renderTiles();
    this.renderHeat();
  }
  renderTiles() {
    const template = this.dataset.tileUrl;
    if (!template || this.projectionName !== "mercator") return;
    const parent = this.svgEl,
      land = parent.querySelector(".map-countries");
    if (!land) return;
    if (this._tileSvg !== parent) {
      this._tileSvg = parent;
      this._tileNodes = new Map();
      this._tileGroup = svg("g", {
        "data-bearings-tiles": "",
        "pointer-events": "none",
      });
      parent.insertBefore(this._tileGroup, land);
    }
    const v = this.view,
      world = 2 * Math.PI * this.projection.scale(),
      z = clamp(Math.floor(Math.log2(world / 256)), 0, 19),
      n = 2 ** z,
      size = world / n;
    const cx = ((v.lon + 180) / 360) * n,
      cy =
        ((1 -
          Math.asinh(
            Math.tan((clamp(v.lat, -85.051128, 85.051128) * Math.PI) / 180),
          ) /
            Math.PI) /
          2) *
        n;
    const center = this.projection([v.lon, v.lat]);
    if (!center || !center.every(Number.isFinite)) return;
    const wanted = new Set();
    const updateState = () => {
      const images = [...this._tileNodes.values()],
        loaded = images.some((i) => i.dataset.state === "loaded");
      land.style.opacity = loaded ? ".08" : "1";
      const state = loaded
        ? "loaded"
        : images.length && images.every((i) => i.dataset.state === "failed")
          ? "unavailable"
          : "loading";
      if (state !== this.dataset.tileState) {
        this.dataset.tileState = state;
        this.dispatchEvent(
          new CustomEvent("bearings-tile-state", { detail: { state } }),
        );
      }
    };
    for (
      let y = Math.floor(cy - center[1] / size);
      y <= Math.ceil(cy + (540 - center[1]) / size);
      y++
    ) {
      if (y < 0 || y >= n) continue;
      for (
        let x = Math.floor(cx - center[0] / size);
        x <= Math.ceil(cx + (960 - center[0]) / size);
        x++
      ) {
        if (wanted.size >= 64) break;
        const key = `${z}/${x}/${y}`;
        wanted.add(key);
        let img = this._tileNodes.get(key);
        if (!img) {
          img = svg("image", {
            width: size + 0.5,
            height: size + 0.5,
            referrerpolicy: "no-referrer",
            "aria-hidden": "true",
          });
          img.dataset.state = "loading";
          img.addEventListener("load", () => {
            img.dataset.state = "loaded";
            updateState();
          });
          img.addEventListener("error", () => {
            img.dataset.state = "failed";
            updateState();
          });
          img.setAttribute(
            "href",
            template
              .replace("{z}", z)
              .replace("{x}", ((x % n) + n) % n)
              .replace("{y}", y),
          );
          this._tileNodes.set(key, img);
          this._tileGroup.append(img);
        }
        img.setAttribute("x", center[0] + (x - cx) * size);
        img.setAttribute("y", center[1] + (y - cy) * size);
        img.setAttribute("width", size + 0.5);
        img.setAttribute("height", size + 0.5);
      }
    }
    for (const [key, img] of this._tileNodes)
      if (!wanted.has(key)) {
        img.remove();
        this._tileNodes.delete(key);
      }
    updateState();
  }
  renderHeat() {
    const parent = this.svgEl;
    let layer = parent.querySelector("[data-bearings-heat]");
    if (!layer) {
      layer = svg("g", { "data-bearings-heat": "", "pointer-events": "none" });
      parent.insertBefore(layer, parent.querySelector(".map-pins"));
    }
    layer.replaceChildren();
    if (!this.heatPoints?.length) return;
    let gradient = parent.querySelector("#bearings-heat-gradient");
    if (!gradient) {
      gradient = svg("radialGradient", { id: "bearings-heat-gradient" });
      gradient.append(
        svg("stop", {
          offset: "0%",
          "stop-color": "#d44218",
          "stop-opacity": ".65",
        }),
        svg("stop", {
          offset: "55%",
          "stop-color": "#eba42a",
          "stop-opacity": ".35",
        }),
        svg("stop", {
          offset: "100%",
          "stop-color": "#eba42a",
          "stop-opacity": "0",
        }),
      );
      parent.querySelector("defs").append(gradient);
    }
    const peak = Math.max(1, ...this.heatPoints.map((p) => p.weight));
    for (const p of this.heatPoints) {
      const xy = this.projection([p.lon, p.lat]);
      if (!xy || !xy.every(Number.isFinite)) continue;
      layer.append(
        svg("circle", {
          cx: xy[0],
          cy: xy[1],
          r: 20 + 35 * Math.sqrt(p.weight / peak),
          fill: "url(#bearings-heat-gradient)",
        }),
      );
    }
  }
}
if (!customElements.get("vt-map")) customElements.define("vt-map", BearingsMap);
if (!customElements.get("vt-stats")) customElements.define("vt-stats", VtStats);
if (!customElements.get("vt-code")) customElements.define("vt-code", VtCode);
// Progressive enhancement leaves ordinary preformatted text available without JS.
for (const pre of document.querySelectorAll(
  ".linux-install-instructions pre, [data-profile-json]",
)) {
  const code = document.createElement("vt-code");
  code.setAttribute(
    "language",
    pre.hasAttribute("data-profile-json") ? "json" : "bash",
  );
  code.setAttribute("copy", "true");
  code.setAttribute("wrap", "true");
  code.setAttribute(
    "label",
    pre.hasAttribute("data-profile-json")
      ? "Validated application profile"
      : "Linux client command",
  );
  code.content = pre.textContent;
  pre.replaceWith(code);
}

// Lazy charts also work in asynchronously refreshed national fragments.
if (!customElements.get("vt-chart")) customElements.define("vt-chart", VtChart);
const pendingCharts = new Set();
function renderTimeline(host) {
  if (!host.isConnected || host.dataset.rendered) return;
  const source = host
    .closest("[data-event-timeline]")
    .querySelector('script[type="application/json"]');
  if (!source) return;
  const chart = document.createElement("vt-chart");
  chart.setAttribute("type", "line");
  chart.setAttribute("height", "280");
  chart.setAttribute("min", "0");
  chart.setAttribute("smooth", "false");
  chart.setAttribute("points", "true");
  chart.setAttribute("tabs", "true");
  chart.setAttribute("label", host.getAttribute("aria-label"));
  const values = JSON.parse(source.textContent);
  const peak = Math.max(0, ...values.series.flatMap((s) => s.data));
  // Retained event counts use integral axis steps, including sparse windows.
  chart.setAttribute("max", String(Math.max(5, Math.ceil(peak / 5) * 5)));
  chart.content = source.textContent;
  host.dataset.rendered = "true";
  host.replaceChildren(chart);
}
const chartObserver =
  "IntersectionObserver" in window
    ? new IntersectionObserver(
        (entries) => {
          for (const entry of entries)
            if (entry.isIntersecting) {
              renderTimeline(entry.target);
              chartObserver.unobserve(entry.target);
              pendingCharts.delete(entry.target);
            }
        },
        { rootMargin: "100px" },
      )
    : null;
function enhanceTimelines() {
  for (const host of pendingCharts)
    if (!host.isConnected) {
      chartObserver?.unobserve(host);
      pendingCharts.delete(host);
    }
  for (const host of document.querySelectorAll(
    "[data-timeline-host]:not([data-rendered])",
  )) {
    if (pendingCharts.has(host)) continue;
    if (chartObserver) {
      pendingCharts.add(host);
      chartObserver.observe(host);
    } else renderTimeline(host);
  }
}
enhanceTimelines();
new MutationObserver(enhanceTimelines).observe(document.body, {
  childList: true,
  subtree: true,
});
