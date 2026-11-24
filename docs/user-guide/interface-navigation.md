# Interface orientation

The workspace uses a consistent set of first-party line pictograms beside visible
labels. Building/globe symbols identify the company/national switch; server,
terminal, shield, flag and envelope shapes distinguish inventory, Linux clients,
vulnerability review, risk and notifications. The same vocabulary appears in the
sidebar, mobile menu, breadcrumbs, workflow steps and national indicator cards.
Symbols identify destinations or topics, not a new affectedness, safety or
verification assessment. Existing numbers, labels, selected states and role-based
navigation remain authoritative.

On long desktop pages, navigation and its explanatory note scroll together in a
bounded sticky container. On small screens, open **Workspace menu** for the same
permitted destinations. Icons never introduce extra tab stops or replace link
names; decorative SVG is hidden from assistive technology.

## Finding the graphs

The **Indicator history** section presents three prominent disclosure tiles with
an icon, heading, short description and **View chart** action. Click anywhere on
the summary or focus it and press Enter/Space. The action changes to **Hide chart**
and the chevron rotates when open. The underlying controls remain native HTML
`details`/`summary`; exact daily values stay available without the chart engine.
The same disclosure style marks company review decisions and Linux report activity.
This presentation does not change history capture, permissions or chart values.

Icons are inline SVG served by the application, with no external icon font, CDN,
tracking or JavaScript requirement. Shapes are fixed and allowlisted in
`portal/templatetags/ui_icons.py`; unknown names use a neutral fallback, never
caller-provided SVG. First-party shapes are covered by the repository license.
Reduced-motion preferences disable chevron animation; focus outlines and visible
text remain present.

## Updating

After checking out the reviewed release:

```sh
./deploy/ubuntu24/manage.py collectstatic --noinput </dev/null
systemctl restart bearings-web
```

Refresh the browser. This presentation update needs no database migration,
national/ordinary-worker restart or Linux client rebuild/restart. The web restart
also loads the new Django template-tag library. Indicator-history recording still
requires its previously documented migration 0067 and national worker.
