# Optional RT / RTIR hand-off

Implemented bounded adapter for **RT 5.x REST2**, alongside FlowIntel. Contract tests and PostgreSQL concurrent-claim tests cover the adapter; the optional [RT 5 reference lab](../operations/rt-lab.md) exercises the real server, queue isolation, hand-off and SSO. Customer RT/RTIR deployments still require acceptance. The adapter also accepts the native typed `EffectiveId` ticket reference and rejects merged/foreign effective identities. Source reviewed: [Best Practical RT 5.0.10](https://github.com/bestpractical/rt/tree/rt-5.0.10), REST2 ticket/search resources and tests. Validate the selected RTIR version and queue custom-field requirements locally.

A platform administrator configures an `RTInstance`: approved HTTPS base/browser URL, numeric queue, `RT_*TOKEN` credential reference, optional fixed numeric custom fields, org binding and explicit private-destination approval. Store the token server-side, outside Git. REST2 uses `Authorization: token …`. API permissions must support creating and reading this queue and searching the generated correlation subject. An org-bound connection is visible to that workspace; a connection without an organization is a CIRCL-only service queue, constrained by current operator visibility.

Enable the connection only after verifying queue ACLs and scrips, and check **private_queue_confirmed**. Ticket creation can trigger RT mail scrips even when no Requestor/Cc/Bcc is supplied. Configure a suitable queue and service account. An issue does not automatically become an RTIR incident; RTIR escalation and Investigation relationships require the dedicated coordination configuration below. The optional bundled RT 5 service uses synthetic private queues and local-only mbox mail.

Open an asset issue and **Prepare RT ticket**. The exact local subject/content/destination preview includes the asset location, issue evidence, reason and pinned risk references. Its creator approves export. Current active issue/asset, sharing, actor, queue and evidence are checked again before I/O. The worker commits its claim before one POST to `/REST/2.0/ticket`. It reads back ID, queue, generated subject and merge identity before exposing a verified ticket link.

Run a worker with deployment credentials loaded:

```sh
uv run python manage.py process_rt_tickets --all --due
```

The bundled worker includes this command. Repeated/concurrent workers do not create duplicate POSTs. An uncertain creation is reconciled using bounded read-only search for the exact queue/subject; no blind POST retry. Remote URLs in API responses are ignored. Status/owner/due-date refresh is separate workflow feedback; completion never patches inventory, changes applicability or closes an issue. Access/transport failure retains the last known state. Revoked visibility suppresses read access and further hand-off. For Plum-derived issues, a withdrawn company source grant also blocks export even when CIRCL retains internal investigation access.

HTTPS verification, bounded JSON, timeouts and redirect refusal apply. The bundled native RTIR workflow is covered by live local tests. Independently deployed queue scrips, production service accounts, remote retention and customer permission tests remain installation acceptance work.

Human sign-in can use the same OIDC provider through the [RT Apache SSO deployment bundle](../operations/rt-sso.md). The REST2 service token remains separate, and its authentication/queue permissions must be checked after deployment. No RT instance or production ticket/mail behavior is provisioned by the generator.


## Native RTIR Incidents and Investigations

The optional [RTIR 5.0.10 lab](../operations/rtir-lab.md) adds `up --rtir`, shared RT SSO and the **RTIR coordination** view. An RTIR connection has `product=rtir`, a distinct `incident_queue_id` and Investigation `queue_id`, no organization binding and an independent server-side credential. Configure native `incidents` and `investigations` lifecycles, including SeeQueue/ShowTicket/CreateTicket and the native ModifyTicket linking right on both queues. Existing generic `product=rtir` entries must be reviewed and explicitly supplied with the correct Incident queue; they are not silently converted or repointed.

An approved Incident is a coordinating ticket anchored to the starting issue. Separately approved Investigations retain individual company/asset/issue evidence, and use native `MemberOf` on creation. Parent identity is part of the approved fingerprint; cross-connection or unverified parents are denied. Read-back and GET-only reconciliation verify native lifecycle and the exact single parent, as well as queue, subject and effective ID. URLs supplied by RT are not followed. An aggregate is visible only while the actor retains access to every participating company. These graphs expose only the relationships managed and verified by Bearings; arbitrary external RTIR links and extra ticket types are not imported.
