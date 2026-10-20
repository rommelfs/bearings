# Plum Island

Status: **bounded historical adapter and comparator implemented; live deployed-instance compatibility not yet validated**. Reference inspected 2026-10-16: [official search documentation](https://github.com/D4-project/Plum-Island/blob/main/documentation/search.md). No deployed release is certified. Verify authentication transport and selected instance permissions/schema before enabling a connector.

Documented endpoint: `GET /api/v1/infoip/<ip>`, individual public IPv4/IPv6 only; CIDR returns 400. Protected permission is `can_get` on `InfoIpApi`; the documented Read Only role gains it after role synchronization. The reader accepts an operator-provisioned Flask-AppBuilder API JWT as a Bearer token. Its permissions/issuance must be verified against the deployed Swagger contract; Agent keys are not accepted.

Default rolling window is 30 days. Use `days` or both `start` and `stop`, not both approaches. Dates are UTC; aware ISO datetimes work. Earliest start is two calendar years back, future stop rejected. Selection uses report `last_seen` within the window; returned `first_seen` may precede it. First/last are not evidence of continuous availability. These are historical observations, not present open-port claims.

404 means never indexed; a known address with no matching-window observations returns empty `ports`. Preserve this distinction. Entries include port, protocol (tcp/udp, possibly null for historical incomplete indexes), tags and first/last timestamps. TCP and UDP on one port are distinct. Tags co-occur at report level and may not identify that port's service. Preserve requested hostname and virtual-host context where available.

Do not blindly enumerate address ranges around a per-IP API. Investigate supported query/export interfaces for networks/domains, including the documented `net:` and `fqdn_requested` search fields. Observation ingestion must preserve provenance, requested window, uncertainty, permission and ingestion/evaluation time. Exposure and inventory discrepancy findings prompt review; tags must never establish vulnerability applicability. Connecting inventory is not a scan-submission action; any later scan coordination must use the configured operational mandate/scope and profiles.

## Source review for the additional phase (2026-10-20)

Reviewed public main commit [`06972ba8d462a537aaeb6b58815d1c6165d084df`](https://github.com/D4-project/Plum-Island/tree/06972ba8d462a537aaeb6b58815d1c6165d084df). This is source research only; a later read-only attempt to retrieve the operator-provided `/v1/swagger` timed out from the cloud; no deployed schema or credentials were obtained and no scans were submitted. CIRCL reports an existing Luxembourg scanning mandate and a large observation corpus; [phase 5a](../roadmap.md) starts with those observations, while phase 5b separately covers optional scan coordination. Internal endpoints and operational datasets are not included in public configuration/examples.

Source-confirmed distinctions:

- [`InfoIpApi`](https://github.com/D4-project/Plum-Island/blob/06972ba8d462a537aaeb6b58815d1c6165d084df/webapp/app/apis.py) uses Flask-AppBuilder `@protect()` and `can_get`. The general API authentication/deployed account contract still needs verification. Scanner `AGENT_KEY` credentials belong to `/bot_api` and must not be assumed to authorize this reader.
- The [`search documentation`](https://github.com/D4-project/Plum-Island/blob/06972ba8d462a537aaeb6b58815d1c6165d084df/documentation/search.md) supports `net:` and requested-hostname filtering. InfoIP selects documents by `last_seen`; expanded history/full exports instead select overlapping seen intervals. These windows are not interchangeable, and first/last aggregates do not reconstruct every scan.
- [`KVSearchView`](https://github.com/D4-project/Plum-Island/blob/06972ba8d462a537aaeb6b58815d1c6165d084df/webapp/app/views.py) has authenticated search and asynchronous full/IP export jobs with owner-checked status/download. These are session-protected UI routes (`@has_access`), not a verified token-authenticated bulk service API. A supported headless export contract is a design gate; do not scrape unbounded datasets or bypass permissions.
- `POST /targets_api/bulk_import` registers targets and queues them for scanning. It is not a data retrieval API. [`Plum-Agent`](https://github.com/D4-project/Plum-Agent) executes scans; Island schedules work and receives results.
- [`scan-profile completion`](https://github.com/D4-project/Plum-Island/blob/06972ba8d462a537aaeb6b58815d1c6165d084df/documentation/scanning.md) can also advance for unrouted targets skipped with ASN 0 and no scan JSON. Such completion is not proof that ports were tested or closed.

A disappearing port in a rolling window, empty response, incomplete scan or unavailable index is **not confirmed closure**. The implemented bounded comparator preserves source/report identity, protocol/port and hostname context, time-valid customer attribution, comparable scan coverage, observed vs ingested time and uncertainty. New exposures are review cues for configuration/service/possible compromise issues; tags or port presence do not prove malware or vulnerability affectedness.

Keep the national corpus in its authoritative source and ingest scoped, resumable, bounded observations. Match selected network/time windows; do not loop over every possible address or transfer all national raw data to company instances. A protected HTTPS operator endpoint/gateway and private runtime credentials will be needed for the existing connector policy; no endpoint, token or transport exception is configured by this planning change.

## Implemented workflow

Configure a platform-managed `PlumInstance` with approved HTTPS endpoint, `PLUM_*TOKEN` reference, optional private-destination approval and explicit company read grants. A DEBUG-only fixture source performs no network requests. The internal source address remains outside public configuration. For the existing HTTP service, use an operator-managed HTTPS gateway with verified certificates; TLS is not bypassed.

**Exposure history** accepts bounded existing InfoIP JSON or a full JSON export selected in Plum for the relevant company and time range. Browser uploads are limited to 2 MB; the operator command reads at most 32 MiB, 2,000 IP entries and 10,000 reports per atomic import:

```sh
uv run python manage.py import_plum --instance approved-source --organization customer-slug --actor authorized-editor --file customer-window.json
```

A verified, historically valid IP/network/range claim must cover each whole requested window. Claim attributes are pinned and checked again at read time. Company users need the source's explicit organization grant; CIRCL uses the current operator policy. Shared/ambiguous inventory mappings remain unresolved; no NetBox asset is fabricated. Only scoped normalized fields, provenance hash and bounded report IDs are retained, not the national raw corpus. This pilot imports complete bounded partitions idempotently; automatic export jobs, source checkpoints and national-scale delta refresh remain future work.

InfoIP GET supports one public IP/window through the connector service; there is no range enumeration or scheduled per-IP fanout. Authentication errors and failed reads remain failures. An explicit 404 is `not_indexed`; a successful empty window is distinct. Full export intervals are overlap-based; the importer conservatively accepts evidence only when its `last_seen` falls in the requested window. Earlier `first_seen` values are withheld when outside that window. Malformed/truncated/warning-bearing exports fail atomically, retaining previous snapshots.

Compare snapshots of the same source/customer/IP/asset. TCP, UDP and requested-hostname contexts remain separate. Cards distinguish newly observed, still observed, changed evidence, not observed, filtered, unknown protocol and **explicit closure reported**. Missing ports never imply closure, remediation or malware. Coverage is explicitly incomplete/unknown; overlapping windows are identified. A mapped positive/explicit observation can prepare an exposure issue with a review reason; no priority, risk scenario, ticket, notification or vulnerability affectedness is inferred automatically. Repeating creation opens the existing review and preserves its decisions.

See the [synthetic exercise](../user-guide/asset-issues.md). No live national/customer observations, Swagger contents or scan submissions were used in validation.
