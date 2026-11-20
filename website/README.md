# Bearings static project website

Company-first SaaS introduction in **English, German, French and Luxembourgish**. Includes practical benefits, company/CIRCL workflows, nineteen FAQs, four synthetic product screenshots, locally hosted project logos and five source-backed real vulnerability examples with explicitly fictional, humorous quotes.

The existing Bearings web service now serves this public introduction at `/`, including `/en/`, `/de/`, `/fr/`, `/lb/` and their FAQs. Login and free registration use the same origin (`/accounts/login/` and `/register/`); the authenticated infrastructure overview is at `/infrastructure/`. No inventory is exposed on these public pages. This change prepares the requested production routing; updating the running server remains an operator action.

The content is HTML/CSS/JavaScript with no visitor analytics or private connectors. The standalone static preview remains available below. Optional FAQ search and screenshot enlargement work in the browser; content remains available without JavaScript.

## Build and preview

From the repository root:

```sh
python3 scripts/dev.py website --language de
```

This command builds the pages and opens the selected language in your browser, without requiring Docker or another build command. Use `--no-open` for a terminal-only session. `python3 website/serve.py` remains available as a standalone server.

The starter builds the pages first and serves an absolute output directory, independent of the caller’s working directory. Stop an older server on port 8050 with Ctrl+C first; it cannot pick up a different serving directory automatically. If the port belongs to another service, use `--port 8051`.

Use **HTTP**, not HTTPS, for this preview. The numeric loopback address avoids Safari carrying over HTTPS-only rules from the separate localhost application. Stop the preview with Ctrl+C. The application stack still starts separately with `python3 scripts/dev.py up --no-build`.

Open:

- English: `http://127.0.0.1:8050/` (also `/en/`)
- Deutsch: `http://127.0.0.1:8050/de/`
- Français: `http://127.0.0.1:8050/fr/`
- Lëtzebuergesch: `http://127.0.0.1:8050/lb/`
- FAQ: add `faq/` to any language path.
- Fictional vulnerability testimonials: follow the link below the main buttons, or open `/de/#testimonials` (the same anchor works in every language).

The registration buttons point to **`https://localhost:9441/register/`**. Start the existing lab with `python3 scripts/dev.py up --no-build` and trust its CA if necessary. For a lab without the integrated HTTPS entrance, use `python3 website/serve.py --registration-url http://localhost:8000/register/`. This changes only the site's links; it does not create users, change the application registration policy or send mail.

## Prepare a later public deployment

No deployment, public hosting workflow or scheduled publishing is installed. When a public Bearings registration service exists, build with both actual origins:

```sh
python3 website/build.py \
  --base-url https://your-project-website.example \
  --registration-url https://your-bearings-installation.example/register/
```

The builder rejects a public website origin combined with a loopback registration target, so localhost is not accidentally advertised publicly. Default local output is marked noindex and disallows crawling; an explicit public origin generates canonical/alternate-language metadata and a sitemap. The marketing pages describe the CIRCL-operated service; local preview/deployment instructions remain in this technical guide.

Copy the **contents of `website/dist/`** to a static HTTPS host. Serve at the origin root: asset/language links are root-relative. A subdirectory mount needs base-path adaptation. Enable directory `index.html` resolution; no SPA fallback is needed. A standalone `404.html` is included. Select the host/custom domain separately when ready; this change does not publish to GitHub Pages or Sites.

## Operator identity

This installation is explicitly identified as operated by **CIRCL**, the CERT for Luxembourg’s private sector and municipalities. The translated operator text describes its statutory CSIRT role under the **Law of 5 May 2026 implementing NIS2**, Article 9 coordinated vulnerability disclosure role, scanning and voluntary information sharing. References: [official CIRCL RFC 2350](https://www.circl.lu/mission/rfc2350/) and [published Luxembourg law](https://legilux.public.lu/eli/etat/leg/loi/2026/05/05/a225/jo). These details are in `copy.json`/`faq.json`; independently operated installations must replace them rather than imply CIRCL operates every deployment.

The NGINX2Root and Java examples also link directly to CIRCL’s [TR-105](https://www.circl.lu/pub/tr-105/) and [TR-104](https://www.circl.lu/pub/tr-104/) alongside the vendor/official sources.

## Visual identity

The header, footer and favicon use a new Bearings mark derived from the supplied CIRCL symbol: a recognizable red aperture surrounded by a teal bearing ring with connecting nodes. The original full CIRCL logo appears below in the operator information. Nine original project logos identify NetBox, Vulnerability-Lookup, MOSP, MONARC, MISP, AIL, FlowIntel, RT and RTIR in their existing ecosystem sections. All assets are local; project links are ordinary outbound navigation. Small screens use a single-column ecosystem layout for readable descriptions. See [branding sources and ownership](branding/README.md) and the [project asset provenance](assets/projects/sources.json).

## Content and maintenance

- `copy.json`: complete EN/DE/FR/LB page copy. Language keys must remain aligned.
- `faq.json`: all four FAQ translations; also generates the canonical English `docs/faq.md`.
- `examples.json`: real CVE IDs, dates, source URLs, factual summaries and separately labeled invented quotes. [Source review](../docs/product/website-examples.md).
- `build.py`: dependency-free HTML and metadata generation.
- `serve.py`: build-before-serve, absolute-directory loopback preview with explicit occupied-port diagnostics.
- `style.css`, `site.js`: responsive presentation and progressive enhancements.
- `assets/`: optimized WebP copies of documented synthetic screenshots and the local Bearings/CIRCL/project marks.
- `dist/`: generated, ignored by Git; building does not modify application data.

Documentation links currently target **`codex/continuous-review-workflow`**, where these guides and implemented features exist. After merging, update `REF` in `build.py`. The displayed content review date is 20 November 2026; update after substantive review. The editorial pass covers all four landing pages, all 76 translated FAQ question/answer pairs, the twenty fictional quotes and their factual/benefit text. Blockquotes render the supplied text once, without automatic outer quotation marks; quotations inside the text retain their language-specific punctuation. Screenshot-window labels, the four workflow words and additional-CVE labels are localized too. French punctuation uses nonbreaking spaces. The FAQ explicitly includes continued free use, current review-schedule permissions and the measured scale results with their limits. Screenshots illustrate synthetic examples and may show an earlier date/UI.

The fictional vulnerability quotes are satire, not real customers, vendor endorsements, attacker statements or observed incidents in a Bearings deployment. The CVEs, dates and source links are real and separately presented. Do not replace dated facts with “currently exploited” claims without checking new primary evidence. No patch-version matrix is duplicated; current vendor guidance remains authoritative.

Keep claims about native MONARC, personal MISP rights/cache limits, manual AIL export, SMTP outcomes, local versus native membership and production readiness consistent with the implementation. The CIRCL-operated Bearings service remains free, including continued use, as confirmed by the product owner; it is not a promise that every independently operated third-party service, support contract or hosting environment is free.

All product screenshots use fictional data. The Luxembourg map retains Natural Earth/GeoNames attribution, including GeoNames CC BY 4.0. Source uses the repository's AGPL-3.0-or-later license; preserve source/license notices. No operational data or private MISP event is included.

## Review before publication

1. Check all four translations and nineteen FAQs against the implementation. Arrange native-language editorial review before an official public launch.
2. Recheck real vulnerability summaries/dates against the linked primary sources; retain the fiction labels and image attributions.
3. Build; check internal links/fragments/assets and JavaScript syntax. Verify all eight pages at desktop/mobile widths, FAQ search/empty state, no-JavaScript content, language navigation, keyboard focus and image dialog.
4. Configure the actual public registration URL, source branch and hostname. Confirm operator-specific legal/privacy information and support contacts without inventing them.
5. Publish only when requested, preserving the chosen hosting identity. Record the returned live URL and source revision.

The public-facing copy focuses on registration for the CIRCL-operated SaaS. Self-hosting/federation promotion and local-start CTAs are intentionally omitted; the loopback preview and developer build instructions here are not part of the landing-page pitch. License/source notices remain.

The current corporate theme follows [circl.lu](https://circl.lu/): locally hosted Raleway, white headers, CIRCL blue/red, neutral surfaces and a blue introductory panel. The same identity applies to the authenticated workspace and administration; risk/status colours remain distinct. See [reference colours, font provenance/license and screenshot scope](branding/README.md#circl-corporate-theme--20-november-2026). Deployment needs normal source update, `collectstatic --noinput` and web-process restart; no new migration or dependency is introduced by the theme.
