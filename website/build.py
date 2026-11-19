#!/usr/bin/env python3
"""Build the public, dependency-free multilingual website and its canonical English FAQ."""

import argparse
import html
import json
import shutil
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
REPO = "https://github.com/rommelfs/bearings"
REF = "codex/continuous-review-workflow"
DOCS = f"{REPO}/blob/{REF}/docs"
FAQ = json.loads((ROOT / "faq.json").read_text())
EXAMPLES = json.loads((ROOT / "examples.json").read_text())
E = html.escape
COPY = json.loads((ROOT / "copy.json").read_text())
LANGUAGES = {"en": "English", "de": "Deutsch", "fr": "Français", "lb": "Lëtzebuergesch"}


def question(item, lang):
    title, answer = item[lang]
    return f'<details class="faq-item" id="{item["id"]}"><summary>{E(title)}</summary><p>{E(answer)}</p></details>'


def figure(file, alt, c, cls=""):
    width, height = {
        "company-actions.webp": (1440, 1050),
        "national-map.webp": (1132, 878),
        "wizard.webp": (1440, 1793),
    }[file]
    return f'<figure class="product-image {cls}"><a href="/assets/{file}" data-lightbox aria-label="{E(c["zoom"])}"><img src="/assets/{file}" alt="{E(alt)}" width="{width}" height="{height}" loading="lazy" decoding="async"></a><figcaption>{E(c["screen"])} <span>{E(c["zoom"])}</span></figcaption></figure>'


def source_links(item, c):
    links = f'<a href="{E(item["source"])}">{E(c["advisory"])}</a>'
    if item.get("context_source"):
        links += f' · <a href="{E(item["context_source"])}">{E(c["context_link"])}</a>'
    if item.get("analysis_source"):
        links += f' · <a href="{E(item["analysis_source"])}">{E(c["analysis_link"])}</a>'
    return links


def page(lang, faq=False, base="", registration="https://localhost:9441/register/"):
    c = COPY[lang]
    home = f"/{lang}/" if lang != "en" else "/"
    faq_url = home + "faq/"
    languages = (
        '<div class="language" aria-label="'
        + E(c["languages"])
        + '">'
        + "".join(
            f'<a href="{("/" if locale == "en" else "/" + locale + "/") + ("faq/" if faq else "")}" lang="{locale}" aria-label="{label}"'
            + (' aria-current="page"' if locale == lang else "")
            + f">{locale.upper()}</a>"
            for locale, label in LANGUAGES.items()
        )
        + "</div>"
    )
    title = c["faq_page_title"] if faq else c["title"]
    canonical = base + (faq_url if faq else home)
    head = (
        f'<link rel="canonical" href="{E(canonical)}"><meta property="og:url" content="{E(canonical)}">'
        if base
        else ""
    )
    alternate = (
        "".join(
            f'<link rel="alternate" hreflang="{locale}" href="{base}{("/" + locale + "/" if locale != "en" else "/") + ("faq/" if faq else "")}">'
            for locale in LANGUAGES
        )
        if base
        else ""
    )
    nav = "".join(
        f'<a href="{home}#{anchor}">{E(label)}</a>'
        for anchor, label in zip(["why", "use-cases", "workflow"], c["nav"][:3])
    )
    start = f'''<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Bearings — {E(title)}</title><meta name="description" content="{E(c["description"])}"><meta name="theme-color" content="#102b37"><meta property="og:type" content="website"><meta property="og:title" content="Bearings — {E(title)}"><meta property="og:description" content="{E(c["description"])}">{head}{alternate}{"<meta name=robots content=noindex>" if not base else ""}<link rel="icon" type="image/svg+xml" href="/assets/mark.svg"><link rel="stylesheet" href="/style.css"><script src="/site.js" defer></script></head><body id="top"><a class="skip" href="#main">{E(c["skip"])}</a><header class="header"><div class="wrap nav"><a href="{home}" class="brand" aria-label="Bearings {E(c["home"])}"><svg viewBox="0 0 36 36" aria-hidden="true"><path d="M18 2 34 18 18 34 2 18Z" fill="none" stroke="currentColor" stroke-width="2"/><path d="M18 9 27 18 18 27 9 18Z" fill="currentColor"/></svg><span class="brand-word">BEARINGS<small>{E(c["operator_short"])}</small></span></a><nav aria-label="{E(c["home"])}">{nav}<a href="{faq_url}">FAQ</a>{languages}</nav><a class="nav-docs" href="{E(registration)}">{E(c["primary"])}</a></div></header><main id="main">'''
    if faq:
        main = f'''<section class="faq-hero wrap"><p class="eyebrow">BEARINGS / FAQ</p><h1>{E(c["faq_page_title"])}</h1><p class="lead">{E(c["faq_intro"])}</p><div class="search" hidden data-search><label for="faq-search">{E(c["search"])}</label><input type="search" id="faq-search" autocomplete="off" placeholder="MISP, NetBox, SSO…"><p aria-live="polite" id="faq-count" data-label="{E(c["results"])}"></p></div><noscript><p>{E(c["nojs"])}</p></noscript><div class="faq-list">{"".join(question(i, lang) for i in FAQ)}</div><p id="faq-empty" hidden>{E(c["empty"])}</p><a class="text-link" href="{DOCS}/README.md">{E(c["nav"][4])}</a></section>'''
    else:
        pillars = "".join(
            f'<article><span class="verb">{E(verb)}</span><h3>{E(title)}</h3><p>{E(body)}</p></article>'
            for verb, title, body in c["pillars"]
        )
        cases = "".join(
            f'<article class="case {"reverse" if n else ""}"><div class="case-copy"><p class="eyebrow">{E(kicker)}</p><h3>{E(title)}</h3><p>{E(body)}</p><ul>{"".join(f"<li>{E(b)}</li>" for b in bullets)}</ul></div>{figure(file, alt, c)}</article>'
            for n, (kicker, title, body, bullets, file, alt) in enumerate(c["cases"])
        )
        steps = "".join(f"<li><h3>{E(title)}</h3><p>{E(body)}</p></li>" for title, body in c["workflow"])
        integrations = "".join(
            f'<article><p class="integration-role">{E(role)}</p><h3>{E(name)}</h3><p>{E(body)}</p></article>'
            for name, role, body in c["integrations"]
        )
        trust = "".join(
            f"<article><h3>{E(title)}</h3><p>{E(body)}</p></article>" for title, body in c["trust"]
        )
        examples = "".join(
            f'<article class="vulnerability"><p class="eyebrow">{E(item["name"])}</p><blockquote>“{E(item[lang]["quote"])}”</blockquote><p class="quote-author"><strong>{E(item["cve"])}</strong><span>{E(c["fiction"])}</span></p><div class="real-fact"><h3>{E(c["fact_label"])}</h3><p>{E(item[lang]["fact"])}</p><h3>{E(c["benefit_label"])}</h3><p>{E(item[lang]["benefit"])}</p>{source_links(item, c)}</div></article>'
            for item in EXAMPLES
        )
        main = f'''<section class="hero"><div class="wrap hero-grid"><div class="hero-copy"><p class="eyebrow">{E(c["eyebrow"])}</p><h1>{c["hero"]}</h1><p class="lead">{E(c["intro"])}</p><div class="actions"><a class="button primary" href="{E(registration)}">{E(c["primary"])}</a><a class="button ghost" href="#workflow">{E(c["secondary"])}</a></div><p class="hero-proof"><a href="#testimonials">{E(c["testimonials_link"])}</a></p><p class="stage"><strong>{E(c["status"])}</strong><span>{E(c["status_note"])}</span></p></div><div class="hero-visual"><div class="window-bar"><span aria-hidden="true">◈</span><span>BEARINGS / INFRASTRUCTURE OVERVIEW</span></div><a href="/assets/overview.webp" data-lightbox aria-label="{E(c["zoom"])}"><img class="hero-shot" src="/assets/overview.webp" alt="{E(c["hero_alt"])}" fetchpriority="high" width="1440" height="1653"></a><p class="hero-caption">{E(c["screen"])}</p></div></div><div class="hero-rule wrap"><span>INVENTORY</span><span>EVIDENCE</span><span>RISK</span><span>RESPONSE</span></div></section>
<section class="operator-band"><div class="wrap"><div><p class="operator-name">{E(c["operator_label"])}</p><p>{E(c["operator_body"])}</p></div><a href="https://www.circl.lu/mission/rfc2350/">{E(c["operator_link"])}</a></div></section>
<section class="section wrap" id="why"><div class="section-intro"><p class="eyebrow">{E(c["why_label"])}</p><h2>{c["why_title"]}</h2><p class="lead">{E(c["why_body"])}</p></div><div class="pillars">{pillars}</div></section>
<section class="section real-examples" id="testimonials"><div class="wrap"><p class="eyebrow">{E(c["real_label"])}</p><h2>{E(c["real_title"])}</h2><p class="lead">{E(c["real_intro"])}</p><div class="vulnerabilities">{examples}</div><p class="small">{E(c["source_note"])}</p></div></section>
<section class="section use-cases" id="use-cases"><div class="wrap"><p class="eyebrow">{E(c["cases_label"])}</p><h2>{c["cases_title"]}</h2>{cases}<p class="small map-note">{E(c["map_note"])}</p></div></section>
<section class="section wrap" id="workflow"><div class="workflow-grid"><div><p class="eyebrow">{E(c["workflow_label"])}</p><h2>{E(c["workflow_title"])}</h2><ol class="steps">{steps}</ol><a class="text-link" href="{E(registration)}">{E(c["get_started"])}</a></div>{figure("wizard.webp", c["wizard_alt"], c, "wizard-shot")}</div></section>
<section class="section ecosystem"><div class="wrap"><p class="eyebrow">{E(c["ecosystem_label"])}</p><h2>{c["ecosystem_title"]}</h2><div class="integrations">{integrations}</div><p class="ecosystem-note">{E(c["ecosystem_note"])}</p></div></section>
<section class="section wrap trust"><p class="eyebrow">{E(c["trust_label"])}</p><h2>{E(c["trust_title"])}</h2><div class="trust-grid">{trust}</div></section>
<section class="section faq-preview"><div class="wrap faq-preview-grid"><div><p class="eyebrow">{E(c["faq_label"])}</p><h2>{E(c["faq_title"])}</h2><a class="text-link" href="{faq_url}">{E(c["faq_all"])}</a></div><div>{"".join(question(i, lang) for i in FAQ if i["id"] in ["operator", "free", "start", "updates", "production"])}</div></div></section>
<section class="section closing wrap" id="register"><div><p class="eyebrow">BEARINGS · AGPL-3.0-OR-LATER</p><h2>{E(c["closing"])}</h2><p class="lead">{E(c["closing_body"])}</p></div><div class="actions"><a class="button primary" href="{E(registration)}">{E(c["primary"])}</a><a class="button secondary" href="{DOCS}/README.md">{E(c["nav"][4])}</a></div></section>'''
    end = f'''</main><footer class="footer"><div class="wrap footer-grid"><div><a class="brand" href="{home}">◈ BEARINGS</a><p><strong>{E(c["operator_label"])}</strong><br>{E(c["operator_body"])}</p><a class="operator-footer-link" href="https://www.circl.lu/mission/rfc2350/">{E(c["operator_link"])}</a></div><div class="footer-links"><a href="{DOCS}/README.md">{E(c["nav"][4])}</a><a href="{faq_url}">FAQ</a><a href="{REPO}/blob/{REF}/LICENSE">{E(c["license"])}</a><a href="#top">{E(c["back"])}</a></div></div><div class="wrap footer-meta"><p>{E(c["privacy"])}<br>{E(c["reviewed"])}</p><p>{E(c["credits"])}<br><a href="https://www.naturalearthdata.com/">Natural Earth</a> · <a href="https://www.geonames.org/">GeoNames</a> · <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a></p></div></footer><dialog id="image-dialog" aria-label="{E(c["zoom"])}"><button type="button" data-close>{E(c["close"])}</button><img alt=""></dialog></body></html>'''
    return start + main + end


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="")
    parser.add_argument("--registration-url", default="https://localhost:9441/register/")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    parsed_base = urlsplit(base)
    if base and (
        parsed_base.scheme != "https"
        or not parsed_base.hostname
        or parsed_base.path
        or parsed_base.username
        or parsed_base.password
        or parsed_base.query
        or parsed_base.fragment
    ):
        parser.error("Use an HTTPS origin without a path")
    registration = urlsplit(args.registration_url)
    if (
        registration.username
        or registration.password
        or registration.fragment
        or registration.query
        or not registration.hostname
        or (
            registration.scheme != "https"
            and not (
                registration.scheme == "http" and registration.hostname in {"localhost", "127.0.0.1", "::1"}
            )
        )
    ):
        parser.error("Use an operator-approved HTTPS registration URL (HTTP is allowed for loopback only)")
    if (
        base
        and urlsplit(base).hostname not in {"localhost", "127.0.0.1", "::1"}
        and registration.hostname in {"localhost", "127.0.0.1", "::1"}
    ):
        parser.error("A public website origin requires an explicit public --registration-url, not localhost")
    assert set(COPY) == set(LANGUAGES) and all(set(item).issuperset(LANGUAGES) for item in FAQ)
    out = ROOT / "dist"
    out.mkdir(exist_ok=True)
    for lang in LANGUAGES:
        for faq in [False, True]:
            target = out / (lang if lang != "en" else "") / ("faq" if faq else "")
            target.mkdir(parents=True, exist_ok=True)
            (target / "index.html").write_text(page(lang, faq, base, args.registration_url))
    # Keep the canonical English URL at / while accepting the intuitive /en/ alias.
    (out / "en" / "faq").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(out / "index.html", out / "en" / "index.html")
    shutil.copyfile(out / "faq" / "index.html", out / "en" / "faq" / "index.html")
    for file in ["style.css", "site.js"]:
        shutil.copyfile(ROOT / file, out / file)
    shutil.copytree(ROOT / "assets", out / "assets", dirs_exist_ok=True)
    (out / ".nojekyll").touch()
    (out / "404.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>Page not found · Bearings</title><h1>Page not found</h1><p><a href="/">Bearings home</a> · <a href="/faq/">FAQ</a></p></html>'
    )
    (out / "robots.txt").write_text(
        ("User-agent: *\nAllow: /\n" + f"Sitemap: {base}/sitemap.xml\n")
        if base
        else "User-agent: *\nDisallow: /\n"
    )
    if base:
        paths = [
            ("/" if locale == "en" else f"/{locale}/") + suffix
            for locale in LANGUAGES
            for suffix in ["", "faq/"]
        ]
        (out / "sitemap.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + "".join(f"<url><loc>{E(base + p)}</loc></url>" for p in paths)
            + "</urlset>"
        )
    if not base:
        (out / "sitemap.xml").unlink(missing_ok=True)
    docs = ROOT.parent / "docs"
    if docs.is_dir():
        text = "# Frequently asked questions\n\nReviewed 2026-11-19. This FAQ describes implemented development/pilot behavior, not production acceptance.\n\n"
        text += "\n\n".join(f"## {i['en'][0]}\n\n{i['en'][1]}" for i in FAQ)
        text += "\n\nSee the [documentation index](README.md), [next steps](product/next-priorities.md) and [validation record](validation.md).\n\nContent source: `website/faq.json`; rebuild with `python3 website/build.py`. The tracking/privacy statement applies to the public static website, not to authentication or logs in a deployed Bearings application.\n"
        (docs / "faq.md").write_text(text)
    print(
        "Built English/German/French/Luxembourgish home and FAQ pages with local assets; no dependencies or private service calls."
    )


if __name__ == "__main__":
    main()
