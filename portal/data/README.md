# Local map data and third-party notices

Downloaded 2026-11-18. Vendored text files normalize line endings to LF and remove trailing whitespace; license wording/source headers are retained. These files contain public geography, no company addresses.

- `lu-postal.json`: 4,519 Luxembourg postal/place/latitude/longitude rows extracted from [GeoNames LU.zip](https://download.geonames.org/export/zip/LU.zip), converted from tab-separated text to compact JSON with the `L-` prefix omitted. [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); original dataset readme is retained as GEONAMES-README.txt. Coordinates can be algorithmically inferred centroids, not building surveys. Attribution appears on the map. Indices cached in memory contain only this public gazetteer; company addresses/results/permissions are not cached.
- Vitrine 0.14.0 now supplies the local Natural Earth world-atlas geometry through its bundled `geo.js`. Component and dependency licenses, pinned source revision and SHA-256 checksums are in `portal/static/portal/vendor/vitrine/`. The previous Leaflet bundles and separate world outline have been removed. Map tiles are hosted separately by CIRCL; see the [map guide](../../docs/user-guide/circl-map.md) for configuration and privacy.

GeoNames `lu-postal.json` SHA-256: `0c1adaaa068c45798a409884745195942383908b53288d227a652d4124a94744`.
