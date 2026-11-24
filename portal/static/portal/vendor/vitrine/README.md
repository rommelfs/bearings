# Vitrine components for Bearings

Upstream: https://github.com/ecrou-exact/vitrine, MIT, version 0.14.0
(prerelease), revision `07ab87825dfbe100b5a3357e4d42b8789f76ffad`.
Only map, stats, code and chart components are exported. `geo.js` includes the local
geographic dependencies. `echarts.js` bundles the upstream Apache ECharts/ZRender
engine, loaded only when a non-empty chart is opened. LICENSE and THIRD_PARTY_NOTICES.md retain upstream
and transitive notices; SHA256SUMS covers generated artifacts.

To reproduce outside the Bearings checkout (Node 24 / npm 11):

```sh
git clone https://github.com/ecrou-exact/vitrine /tmp/vitrine-source
git -C /tmp/vitrine-source checkout --detach 07ab87825dfbe100b5a3357e4d42b8789f76ffad
cd /tmp/vitrine-source
npm ci --ignore-scripts --no-audit --no-fund
cd /path/to/bearings
node scripts/vendor_vitrine.mjs /tmp/vitrine-source
cd portal/static/portal/vendor/vitrine
sha256sum -c SHA256SUMS
```

No npm/build tool is required in production. The unmodified upstream components
are extended by Bearings' `vitrine-widgets.js` for regional zoom, CIRCL XYZ tiles,
weighted heat and pointer-capture marker selection. This adapter is maintained
here; no upstream submission or native Vitrine XYZ support is implied.
