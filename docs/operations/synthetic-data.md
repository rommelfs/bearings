# Exploration data and safe removal

The **bundled development installation** automatically creates the `explore-v1` showcase on its next `python3 scripts/dev.py up`. This also fills an existing lab after an update. External mode and non-DEBUG deployments do not automatically receive it. Set `BEARINGS_SHOWCASE=0` before starting the lab to skip automatic creation. No default passwords or additional application/SSO accounts are created.

As `circl-analyst` or `platform-admin`, follow **Explore the scenarios** in the synthetic-data banner, or open `/explore/`. Visibility follows ordinary company membership and CIRCL sharing policy. Two companies deliberately do not grant CIRCL visibility; platform administrators can still see them. The bundled `company-admin` demonstrates responsibility for exactly one company, `netbox-lab-rw`, and does not receive memberships in these additional showcase companies.

## What is included

The default dataset explicitly tracks its synthetic objects and their ownership:

| Area | Examples |
| --- | --- |
| Organizations | 10 fictional companies; 30 synthetic contacts with different roles/languages/review freshness |
| Inventory | 300 assets; IPv4, documentation IPv6, `.invalid` DNS, datacenter, room, rack/U, serial, tag, platform and responsible team |
| Software | 900 software/firmware installations; Exchange, Log4j, FortiOS, OpenSSH and deliberately unknown example versions |
| Vulnerabilities | 300 reviews; Critical/High/Medium/Low/Unknown source severity, different applicability/status/priority and pinned evidence |
| Lifecycle | 600 support/license/warranty/EOL/maintenance issues; overdue and future dates, disputed and unknown facts, owners and possible consequences |
| Risk | 6 invented MOSP-shaped scenarios, 300 vulnerability risk mappings and 600 lifecycle mappings with pinned revisions |
| Exposure | 180 weekly snapshots for 30 asset/IP mappings over six weeks; 60 linked port-change reviews; ports disappear/appear without claiming confirmed closure or malware |
| Response | 3 offline RTIR Incident previews with 5 Investigations, 4 FlowIntel case previews and 16 tasks |
| Outreach | 10 internal batches, 20 rendered message previews and their evidence links; no approval or delivery |

These additional assets are **offline development fixtures in Bearings**, not imported objects in the bundled NetBox server. Likewise the additional MOSP/Vulnerability-Lookup/Plum evidence and RTIR/FlowIntel previews are clearly synthetic, not newly fetched intelligence or exported backend cases. The existing live bundled connector exercises remain separate. Disabled outbound case/catalog connections, no credentials and draft-only state prevent these previews from becoming remote jobs. Contacts have no verified reachability or outreach opt-in; preview-only fingerprints also prevent approving the canned messages. A new reviewed operational preview is required for real outreach.

Published CVE identifiers are used alongside clearly labeled fictional review evidence; severity/applicability and business consequences in the showcase are not authoritative CVE or MONARC assertions. Documentation addresses (`192.0.2.0/24`, `198.51.100.0/24`, `2001:db8::/32`) and `.invalid` email/DNS are used. No scans, notifications, SMTP, remote provisioning or inventory writes occur during this seed.

The seed is repeatable: it retains the existing dataset, including edits and review decisions, instead of overwriting them. To populate a standalone DEBUG checkout with an existing platform superuser, or choose a smaller first dataset:

```sh
uv run python manage.py seed_showcase --actor YOUR_SUPERUSER --companies 3 --assets-per-company 12
```

In the bundled stack, the explicit equivalent is:

```sh
python3 scripts/dev.py manage seed_showcase
```

Changing size options does not resize or overwrite an existing dataset. Bounds are 1–20 companies, 2–100 assets each, at most 1,000 assets. To deliberately recreate a removed showcase, pass `seed_showcase --restore`; normal startup never restores it.

## Review and remove

Sign in as **platform-admin**, open **Review / remove synthetic data** in the banner (`/administration/synthetic-data/`), inspect the companies, object counts and any blockers, then type the displayed removal phrase and submit. This removes only records owned by this dataset, including its synthetic review histories. Existing users, passwords, SSO bindings, unrelated real records and audit events are preserved. Audit events are detached from removed fictional organizations; the removal itself is audited. A retained `removed` dataset marker prevents automatic reseeding after subsequent restarts.

CLI equivalent, also available with `DEBUG=False` in preproduction:

```sh
python3 scripts/dev.py manage demo_data plan
python3 scripts/dev.py manage demo_data purge --apply --fingerprint REVIEWED_PLAN_HASH
python3 scripts/dev.py manage demo_data check
```

For a non-bundled deployment, use `uv run python manage.py` instead of `python3 scripts/dev.py manage`, and supply `--actor YOUR_SUPERUSER` for removal. `purge` without `--apply` is a preview. The hash must match the current plan; changed review history/object membership requires a new preview. Ordinary company/CIRCL accounts cannot inspect or execute the cleanup. Web removal uses POST and CSRF protection; CLI execution requires an existing active platform superuser.

The application records ownership when it creates each object, rather than inferring it from words such as “SYNTHETIC” in a name. A dry-run reference scan blocks removal if unowned data references any owned object, including real company grants to fixture sources. Changed real recipient addresses, replaced inventory provenance/non-documentation addresses, promoted live connectors, remote case/ticket identities and message receipts also block automatic removal for separate retention review. PostgreSQL row locks recheck the plan and prevent a concurrent real FK insertion from slipping into the deletion. Any error rolls back the complete removal. SQLite remains a one-worker local fallback.

## Before (pre-)production

`demo_data check` exits nonzero while tracked datasets or recognized **unregistered older fixtures** remain. It reports older fixture evidence/Plum sources and known old example organizations; it never adopts/deletes them by their name. This matters for existing installations predating the provenance registry. Review those separately or build the production deployment with clean application databases and explicitly migrated real inventory/policies.

This cleanup does **not** remotely delete examples in NetBox, FlowIntel, RTIR or Keycloak, remove retained volumes, rotate lab credentials, or turn the bundled developer stack into a production deployment. Backend retention and a clean production service/identity configuration remain separate. Exported cases/messages require explicit retention decisions rather than erasing local evidence that still identifies remote objects. No successful local data check certifies the complete deployment as production-ready.

## Luxembourg geography showcase

The existing ten `explore-v1` companies now receive fictional street/address labels with real Luxembourg postcodes/localities: Luxembourg, Esch-sur-Alzette, Differdange, Dudelange, Diekirch, Ettelbruck, Wiltz, Clervaux, Echternach and Remich. These are not real customer offices. The bundled local postal lookup plots approximate locations without geocoding/tiles leaving the application. Ordinary CIRCL visibility is preserved: eight of the ten default companies are visible to CIRCL, and two remain private. No vulnerability decision, priority, scope or notification opt-in is changed to manufacture map colors.

`python3 scripts/dev.py up --no-build` automatically performs the one-time address extension in bundled mode when the showcase is enabled, including retained installations whose init container does not rerun. It respects the container's `BEARINGS_SHOWCASE=0` flag, never recreates a removed dataset, and touches only registry-owned companies/sources with blank addresses, development provenance and no unowned/converted assets or manual map points. Edited/nonblank addresses and deliberately cleared addresses after extension are preserved. Busy source writers are skipped for a later run instead of waiting while an organization lock is held. No NetBox/API write, mail or new account is involved.

Explicit manual command for an existing DEBUG showcase:

```sh
python3 scripts/dev.py manage seed_showcase_addresses
```

Standalone use can pass `--actor YOUR_SUPERUSER`. The extension records processed companies and hashes of the exact synthetic address values in dataset metadata. Cleanup blocks when a nonblank company address differs from its recorded synthetic value, protecting later user/operational edits for separate review. New/retained seeds do not adopt a company merely because its name contains “SYNTHETIC”. [Real SSO showcase map](../images/circl-luxembourg-showcase.png).

## One company per demonstration administrator

Bundled startup and explicit `python3 scripts/dev.py up --no-build` narrow the existing synthetic `company-admin` account to its already assigned read/write NetBox lab company. Retained older lab/showcase memberships are removed with audit events, together with their fixture membership registry entries. CIRCL visibility, platform access, user passwords, SSO bindings and native backend permissions remain intact. General Bearings accounts can still have multiple memberships; this is a demonstration profile only.

The helper requires DEBUG, the explicit bundled-lab flag, a platform administrator and matching local source identities. Unrelated/converted company grants or unexpected operator privileges cause refusal for manual review without partial deletion. It never restores a revoked grant or adds a company membership. External mode is excluded. In a standalone showcase with an existing unassigned `company-admin`, the initial seed gives at most the first synthetic company; repeating a retained seed does not recreate revoked memberships.
