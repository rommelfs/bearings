# Local map data and third-party notices

Downloaded 2026-11-18. Vendored text files normalize line endings to LF and remove trailing whitespace; license wording/source headers are retained. These files contain public geography, no company addresses.

- `lu-postal.json`: 4,519 Luxembourg postal/place/latitude/longitude rows extracted from [GeoNames LU.zip](https://download.geonames.org/export/zip/LU.zip), converted from tab-separated text to compact JSON with the `L-` prefix omitted. [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); original dataset readme is retained as GEONAMES-README.txt. Coordinates can be algorithmically inferred centroids, not building surveys. Attribution appears on the map. Indices cached in memory contain only this public gazetteer; company addresses/results/permissions are not cached.
- `world-outline.geojson`: country names/codes and polygon coordinates extracted from [Natural Earth 1:10m admin-0](https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_10m_admin_0_countries.geojson). [Public domain](https://www.naturalearthdata.com/about/terms-of-use/). Luxembourg/Belgium/France/Germany retain outline vertices; other rings retain every twelfth vertex, at least three points, and closure. Coordinates rounded to five decimals. This is a lightweight geographic backdrop, not a legal boundary or street map. Five public Luxembourg city labels provide orientation.
- Leaflet **1.9.4**, vendored from `https://unpkg.com/leaflet@1.9.4/dist/leaflet.js` and `.css`, uses its own BSD-2-Clause license in `portal/static/portal/vendor/leaflet/LICENSE`. No runtime CDN requests. Circle markers/labels need no external icon images.
- Leaflet.heat / bundled simpleheat: `https://github.com/Leaflet/Leaflet.heat/blob/gh-pages/dist/leaflet-heat.js`, copyright 2014 Vladimir Agafonkin, BSD-2-Clause notice in `HEAT-LICENSE`; source headers preserved. The vendored bundle and license apply to this third-party code; Bearings application code retains AGPL-3.0-or-later.

Integrity of committed files (SHA-256):

- `portal/data/lu-postal.json`: `0c1adaaa068c45798a409884745195942383908b53288d227a652d4124a94744`
- `portal/static/portal/world-outline.geojson`: `07ce45bc42780b0e9aaf53a14b487f2d0a8fbdf1251b53dd346e72e2a3de16a2`
- `portal/static/portal/vendor/leaflet/leaflet.js`: `4f1ac3296897403e0a84881c974dbdf36d9a8488f0ef4b5626a952b1b6190d80`
- `portal/static/portal/vendor/leaflet/leaflet.css`: `337bfca5cabd03b39815b2700febe2b3b7edf55921c59cd49f88ecb328212303`
- `portal/static/portal/vendor/leaflet/leaflet-heat.js`: `31b83e22f1d66f8cf6d2c1747deaffe1fa3e3514105d0f5f63270aa346c4b77d`
