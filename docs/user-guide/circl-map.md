# CIRCL company severity map

Open **National overview** (`/circl/`). The **Company locations and open problems** map loads independently of the existing counters/tables. No additional data processing blocks the initial overview response. Use severity filtering, zoom/pan, **Fit shown companies**, or **Heatmap + markers**. Clicking a marker opens company and exact problem-list links. Co-located/near-identical rounded points form one marker with the highest severity and a multi-company popup. A searchable 50-row-page accessible table provides direct links without map interaction.

## What the colors mean

The highest currently visible outstanding value at a company determines its marker:

| Color | Recorded value |
| --- | --- |
| Red / magenta | Critical vulnerability source severity or Critical issue priority |
| Orange | High source severity or High issue priority |
| Amber | Medium source severity or Review issue priority |
| Blue | Low source severity or Low issue priority |
| Purple | Unrated/unknown/informational source value |
| Grey | No open problems recorded in permitted active inventory |

Vulnerability counts use the canonical review, including legacy reviews without a common issue. Its common issue proxy is not counted twice. Other issues use explicit priority, not a fabricated CVSS score. Accepted risk stays outstanding; resolved, false-positive and not-affected vulnerability reviews are excluded. Retired inventory and malformed source/organization/product lineage are excluded. Exposure-linked issues retain current observation/source/claim visibility. These colors do not prove installed patches, exploitation, compromise or complete coverage; grey is not a safety assessment.

The heatmap shows relative weighted concentration at company locations: severity weights 1–5 multiplied by problem count capped at 20 per company. Weights are normalized against the highest company weight in the filtered view. No-open companies contribute no heat. Density, zoom and co-location affect intensity; it is not a national risk probability or a historical trend. Markers remain clickable in heat mode.

## Local address lookup and manual points

Address lookup runs only against a bundled **GeoNames Luxembourg** postal/place index. No addresses go to a geocoder. An explicit `L-` postal code or Luxembourg country context is required. Unprefixed codes also need a matching place; pure country names, street-name substrings, conflicting codes, explicit foreign-country statements, unknown postal codes and ambiguous places are not guessed. Postal/place coordinates are approximate centroids, not building locations.

The map shows **company locations**, not asset/server locations. Foreign or unresolved addresses can use a manual point. Expand **Companies not located**, choose **Set company point**, click the local map or enter latitude/longitude, then **Save company point**. Manual points can also be corrected from a marker popup. Platform superusers and CIRCL analysts for currently shared organizations can position companies. Membership-only analyst access to a private organization permits its ordinary scoped reads but does not grant map positioning; company accounts cannot open operator map routes.

Saving is an explicit CSRF-protected POST bound to the current organization/address and an expiring signed form. Address changes invalidate the previous manual point. Local lookup then uses the new address if possible; otherwise the company returns to unlocated. Old manual state is not silently attached to a new address. **Remove manual point** returns to local lookup. A manually positioned point does not verify address, jurisdiction or infrastructure authority.

Map status exposes located/unlocated/missing-address counts, unlocated companies with open problems and manual points invalidated by changed addresses. Up to 50 unlocated companies are listed, highest severity/priority first. All must still be considered in the ordinary national/company problem lists. Existing records with blank addresses remain blank. Add an address through the company page or position the company manually; no synthetic or real company is assigned an invented location automatically.

## Privacy, scope and scaling

The authenticated `/circl/map/data/` request independently enforces current operator roles and organization/source/evidence policy, audits the aggregate read without addresses/criteria, and sends a private/no-store response. No cross-user response/authorization/result cache is used. Only the public gazetteer index is cached in memory. Markers carry company names/counts and scoped links, not raw addresses/evidence. Manual-point mutation is scoped and audited without raw coordinates/address in audit metadata. Popups/tables use text nodes for untrusted names.

Leaflet, heat rendering, outlines and approximate place data are bundled locally with their licenses/attribution. No runtime tiles, CDN, geocoder or analytics are contacted. Static world outlines are a lightweight backdrop, not a street-level or authoritative boundary map. Public third-party geography provenance/checksums: [map notices](../../portal/data/README.md). The first geographic-backdrop request is about 1.3 MB and can be statically cached; company data cannot.

Database work is grouped by organization and points are streamed through a bounded highest-priority selection, with no per-company database/geocoder request. At most **2,000 located company markers** are returned. Higher-severity and then higher-count companies come first; status explicitly reports omitted located companies. This is a transparent response bound, not an exhaustive geographic view beyond that limit. Exact per-company problem lists remain available independently. Map failures/timeouts clear stale markers and show a retry message while the ordinary overview remains usable. The overview's existing 60-second refresh updates the map too; **Refresh map** rereads current permissions immediately.

Migration 0032 adds manual organization locations with coordinate-range constraints. Run `git pull` then `python3 scripts/dev.py up --no-build` to migrate/restart. The bundled static geography requires no service/API configuration.
