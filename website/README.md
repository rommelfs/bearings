# Bearings static project website

Company-first introduction in **English, German, French and Luxembourgish**. Includes practical benefits, company/CIRCL workflows, nineteen FAQs, four synthetic product screenshots and five source-backed real vulnerability examples with explicitly fictional, humorous quotes.

**Local-only at the owner's request. Nothing has been deployed publicly.** The main call to action is free company registration at the existing local Bearings installation. The website is static HTML/CSS/JavaScript, with no dependencies, visitor analytics, forms, cookies or private connectors. Optional FAQ search and screenshot enlargement work in the browser; content, answers and image links remain available without JavaScript.

## Build and preview

From the repository root:

```sh
python3 website/build.py
python3 -m http.server 8050 --directory website/dist --bind 127.0.0.1
```

Open:

- English: `http://localhost:8050/`
- Deutsch: `http://localhost:8050/de/`
- Français: `http://localhost:8050/fr/`
- Lëtzebuergesch: `http://localhost:8050/lb/`
- FAQ: add `faq/` to any language path.

The registration buttons point to **`https://localhost:9441/register/`**. Start the existing lab with `python3 scripts/dev.py up --no-build` and trust its CA if necessary. For a lab without the integrated HTTPS entrance, use `python3 website/build.py --registration-url http://localhost:8000/register/`. This changes only the site's links; it does not create users, change the application registration policy or send mail.

## Prepare a later public deployment

No deployment, public hosting workflow or scheduled publishing is installed. When a public Bearings registration service exists, build with both actual origins:

```sh
python3 website/build.py \
  --base-url https://your-project-website.example \
  --registration-url https://your-bearings-installation.example/register/
```

The builder rejects a public website origin combined with a loopback registration target, so localhost is not accidentally advertised publicly. Default local output is marked noindex and disallows crawling; an explicit public origin generates canonical/alternate-language metadata and a sitemap. Remove the local-preview note by configuring a non-loopback registration URL.

Copy the **contents of `website/dist/`** to a static HTTPS host. Serve at the origin root: asset/language links are root-relative. A subdirectory mount needs base-path adaptation. Enable directory `index.html` resolution; no SPA fallback is needed. A standalone `404.html` is included. Select the host/custom domain separately when ready; this change does not publish to GitHub Pages or Sites.

## Content and maintenance

- `copy.json`: complete EN/DE/FR/LB page copy. Language keys must remain aligned.
- `faq.json`: all four FAQ translations; also generates the canonical English `docs/faq.md`.
- `examples.json`: real CVE IDs, dates, source URLs, factual summaries and separately labeled invented quotes. [Source review](../docs/product/website-examples.md).
- `build.py`: dependency-free HTML and metadata generation.
- `style.css`, `site.js`: responsive presentation and progressive enhancements.
- `assets/`: optimized WebP copies of documented synthetic screenshots and a local SVG mark.
- `dist/`: generated, ignored by Git; building does not modify application data.

Documentation links currently target **`codex/continuous-review-workflow`**, where these guides and implemented features exist. After merging, update `REF` in `build.py`. The displayed content review date is 19 November 2026; update after substantive review. Screenshots illustrate synthetic examples and may show an earlier date/UI.

The fictional vulnerability quotes are satire, not real customers, vendor endorsements, attacker statements or observed incidents in a Bearings deployment. The CVEs, dates and source links are real and separately presented. Do not replace dated facts with “currently exploited” claims without checking new primary evidence. No patch-version matrix is duplicated; current vendor guidance remains authoritative.

Keep claims about native MONARC, personal MISP rights/cache limits, manual AIL export, SMTP outcomes, local versus native membership and production readiness consistent with the implementation. Free company registration is the product owner's stated offer; it is not a promise that every independently operated third-party service, support contract or hosting environment is free.

All product screenshots use fictional data. The Luxembourg map retains Natural Earth/GeoNames attribution, including GeoNames CC BY 4.0. Source uses the repository's AGPL-3.0-or-later license; preserve source/license notices. No operational data or private MISP event is included.

## Review before publication

1. Check all four translations and nineteen FAQs against the implementation. Arrange native-language editorial review before an official public launch.
2. Recheck real vulnerability summaries/dates against the linked primary sources; retain the fiction labels and image attributions.
3. Build; check internal links/fragments/assets and JavaScript syntax. Verify all eight pages at desktop/mobile widths, FAQ search/empty state, no-JavaScript content, language navigation, keyboard focus and image dialog.
4. Configure the actual public registration URL, source branch and hostname. Confirm operator-specific legal/privacy information and support contacts without inventing them.
5. Publish only when requested, preserving the chosen hosting identity. Record the returned live URL and source revision.
