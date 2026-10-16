# MOSP / MONARC scenario catalog

Implemented: public, read-only MOSP v2 access to MONARC risk templates and their asset-type, threat and general-weakness definitions. The default endpoint is `https://objects.monarc.lu`, publisher `MONARC`, language `EN`. This connects existing NetBox inventory and Vulnerability-Lookup evidence in an organization-scoped **Asset → Vulnerability → Risk** view. It does not require a MONARC application server.

MONARC's catalog `vulnerability` means a general organizational weakness, such as flawed patch management. It is not a CVE. A catalog risk is a reusable scenario, not an organization's assessed or accepted risk. No CVE-to-risk key or automatic matching is assumed. The user selects a scenario and records why it may matter; applicability, workflow, likelihood, impact, residual risk and acceptance remain separate. No organizational patch-management weakness is inferred from a CVE.

## Start and use

Update/rebuild the retained development environment (database and secret volumes are preserved):

```sh
git pull
python3 scripts/dev.py up
python3 scripts/dev.py manage sync_mosp --all
```

The development initializer registers the public source without making a remote request. The worker refreshes enabled catalogs at their configured interval (default daily), after inventory jobs. For a bare-host environment run migrations, then `uv run python manage.py sync_mosp --all`; repeat `--source <id>` to select particular sources. `--due` applies interval scheduling. Commands finish unsuccessfully if a source fails, after processing the remaining sources.

1. Sign in and open an organization with imported NetBox inventory. Select an asset and record an explicit software/product identity and version; NetBox device names do not establish installed software.
2. Retrieve a CVE through the existing Vulnerability-Lookup form. The bundled NetBox seeds include a synthetic Log4j installation for this exercise; `CVE-2021-44228` can be retrieved live. The separate `example-labs` fixture remains labeled synthetic.
3. Open **Asset → Vulnerability → Risk**, choose **Link a risk scenario**, and browse/search the cached catalog. Select a template or supply a known risk UUID. Verify that its catalog asset type, threat and weakness fit the actual case, then provide a justification.
4. The link verifies all four MOSP objects live and pins their content together with the current CVE evidence. Use the pinned evidence link to inspect provenance and hashes. A mapping can be withdrawn with a reason; the original evidence and justification remain in history. Repeating an identical active mapping retains the original justification.

Every external operation is a GET. Only a requested CVE ID is sent to Vulnerability-Lookup; only public schema, language, publisher and catalog UUID filters are sent to MOSP. Inventory, organization names and mapping justifications are not transmitted. Requests are user/operator initiated or development-worker catalog refreshes; there are no scans, upstream writes or notifications.

## Contract and operator settings

The adapter uses `GET /api/v2/schema/` and `GET /api/v2/object/`. Inspected live on 2026-10-16: metadata `count`, `offset` and `limit` are strings, `offset` is the zero-based page index, and there are 1,938 MONARC risk templates. Risk objects have no language field; definitions are filtered by the source language. Schemas are identified by their known UUID and publisher, rather than deployment-local integer IDs. A different publisher also reuses a schema UUID, so UUID matching alone is insufficient.

Only explicitly `CC0-1.0`-licensed objects are accepted. Publisher, schema, identity, references and definition language are verified. The adapter does not resolve remote JSON Schema references or import measures/standards text. Software licensing is distinct from catalog/data rights; no rights to unrelated standards are implied.

`MOSP_URL` and `MOSP_PUBLISHER` initialize the default source only. Platform superusers manage sources in Django administration; participants select an approved source, never an arbitrary URL. Endpoint/publisher/language cannot be changed after import; create a new source for a different identity. Other MOSP installations are supported only when they implement this public CC0 MONARC schema contract; authenticated/private catalogs and synchronization with a deployed MONARC assessment are future work.

Requests require credential-free HTTPS, verified certificates, no redirects, fixed locally constructed pagination, 15-second per-request timeouts and the shared 2 MB response bound. Traversals are limited to 100 pages / 10,000 objects. Duplicate identities, changed counts, incomplete pages and malformed records fail the complete refresh. Only complete source snapshots update catalog membership. Missing objects are retained and flagged; failures retain last-known data, links and last-success timestamps. Upstream update dates and local receipt dates are distinct: a successful fetch does not make an old definition new.

Ordinary development uses direct DNS. For an approved proxy-only environment, `MOSP_PROXY_DNS=1` and `VULNERABILITY_LOOKUP_PROXY_DNS=1` enable proxy DNS for the public connectors independently of internal NetBox traffic. Set `CONNECTOR_ALLOWED_HOSTS=vulnerability.circl.lu,objects.monarc.lu`, inject the approved HTTPS proxy securely, and retain the approved CA chain. These flags default to the global `CONNECTOR_PROXY_DNS` setting; the bundled Docker lab keeps the global setting off for internal NetBox. Runtime Docker networking/trust must be configured separately from build-time proxy forwarding. Production egress policy must enforce approved destinations against DNS rebinding.

## Evidence and visibility

CVE evidence revisions are content-addressed snapshots; refreshing an existing record preserves its operator-owned `shareable` policy. Links pin a complete risk/asset/threat/weakness bundle and a particular CVE revision. Catalog-root changes, missing objects, disabled sources and changed CVE evidence produce review flags without rewriting the link. Referenced definition-only changes are detected when that bundle is resolved again; background refresh currently fetches root templates, not every linked definition. No automatic re-assessment or score is produced.

Organization members and explicitly authorized CIRCL analysts can read the joined view according to the existing raw/derived evidence policy. Editors/admins and authorized operator reviewers can create or withdraw links. Revoking visibility or restricting source evidence removes the derived links from participant pages and APIs too. Catalog definitions themselves are public; local mappings and reasons are organization-owned.

Session-authenticated endpoints:

- `/api/v1/organizations/<slug>/intelligence/`: paginated inventory/software/finding/scenario chains with independent assessment state.
- `/api/v1/organizations/<slug>/risk-links/<id>/evidence/`: pinned CVE and catalog evidence plus hashes and review flags.

The existing finding evidence endpoint returns the current CVE record. Pinned endpoints retain the evidence used in an older mapping. Snapshot protection is enforced by application services and protected relationships; database administrators remain trusted. Schema adapters, complete aliases, automated applicability, likelihood/impact scoring, risk ownership/treatment/acceptance and a full MONARC import/export remain backlog work.
