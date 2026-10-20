# Independent company instances: bounded read-only pilot

Implemented: explicit company export grants, a versioned bounded complete-snapshot endpoint, operator-configured company readers, retained source reports and a **Company instances** view. This is a first pilot; production delta feeds, partitioning/checkpoints, remote acknowledgments, SSO and outreach from federated data remain future work. Hosted company workspaces continue to use the existing organization model and NetBox instances.

An active company administrator (or trusted platform administrator) grants access for one organization's explicitly shareable, non-operator-only issues. Inventory needs an additional explicit grant. CIRCL group membership alone cannot grant a company's data. Current publisher membership, account, grant expiry, source restrictions and historical Plum scope are checked on each request. Only a token digest is stored. Export identity is a pseudonymous grant UUID, bound to a receiver-generated client UUID and an operator-pinned HTTPS endpoint; it is not a numeric local organization ID.

On the receiving instance a platform administrator creates a disabled `CompanyInstance`, selects the local company workspace and approved HTTPS endpoint, and obtains its `client_id`. Use that ID on the company's own instance:

```sh
uv run python manage.py grant_federation --actor company-admin --organization customer-slug --client RECEIVER-CLIENT-UUID --output /private/new-federation-token --days 30
```

Add `--inventory` only for inventory sharing. The command prints the grant/export UUID, writes the bearer credential to a new mode-0600 file and never prints it. Transfer the file through the operator's secure credential process. Configure the receiver's `remote_organization` with that **grant/export UUID** and a `FEDERATION_*TOKEN` environment reference. Grant lifetime is 1–90 days; disable it in source administration to revoke new reads. Do not put tokens into commands, URLs or Git. Load private runtime credentials and enable the approved connection, then:

```sh
uv run python manage.py pull_company --instance approved-company
```

The client only GETs `/api/v1/federation/export/`, sends Bearer credentials plus `X-Bearings-Client`, verifies HTTPS, rejects redirects and ignores response-provided URLs. The server requires HTTPS; behind a proxy use an operator-managed trusted HTTPS forwarding configuration. Each complete snapshot is capped at **500 issues and 500 assets, 1.5 MB total**. Above the limit it refuses the whole export; it does not silently truncate. The client validates schema, export identity, timestamp, duplicate IDs and complete shape before a source-locked atomic import. Older concurrent reads cannot overwrite a later-started refresh. The first pilot exports issue summaries/consequences and optional allowlisted asset location fields; raw intelligence, contacts and credentials are excluded.

Reports remain company-reported records; no authoritative local Asset, Finding or Installation is created/overwritten, and they cannot enter bulk outreach. Missing records/withdrawn inventory permission retain history with a missing marker. Failed reads retain last-known data and an error. Freshness older than one hour is labelled stale; a successful pull is not continuous connectivity. Scope revocation stops future source reads; **previously exported copies are not remotely erased**. Local organization/operator policies govern access to retained copies; disabling the local connection hides its reports. Agree retention and revocation procedures before operational use.

No real company instance was contacted in this increment; automated contract tests exercise authentication, sharing, TLS-required ingress, expiry, isolated UI, partial/duplicate/stale snapshots and atomic retention. A live two-instance pilot and large-corpus delta contract are still required.
