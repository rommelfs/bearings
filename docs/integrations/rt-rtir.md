# Optional RT / RTIR hand-off

Implemented bounded adapter for **RT 5.x REST2**, alongside FlowIntel. Contract tests and PostgreSQL concurrent-claim tests cover the adapter; **no live RT/RTIR deployment is certified**. Source reviewed: [Best Practical RT 5.0.10](https://github.com/bestpractical/rt/tree/rt-5.0.10), REST2 ticket/search resources and tests. Validate the selected RTIR version and queue custom-field requirements locally.

A platform administrator configures an `RTInstance`: approved HTTPS base/browser URL, numeric queue, `RT_*TOKEN` credential reference, optional fixed numeric custom fields, org binding and explicit private-destination approval. Store the token server-side, outside Git. REST2 uses `Authorization: token …`. API permissions must support creating and reading this queue and searching the generated correlation subject. An org-bound connection is visible to that workspace; a connection without an organization is a CIRCL-only service queue, constrained by current operator visibility.

Enable the connection only after verifying queue ACLs and scrips, and check **private_queue_confirmed**. Ticket creation can trigger RT mail scrips even when no Requestor/Cc/Bcc is supplied. Configure a suitable queue and service account. An issue does not automatically become an RTIR incident; ticket classes/relationships depend on that installation. No bundled RT service is included.

Open an asset issue and **Prepare RT ticket**. The exact local subject/content/destination preview includes the asset location, issue evidence, reason and pinned risk references. Its creator approves export. Current active issue/asset, sharing, actor, queue and evidence are checked again before I/O. The worker commits its claim before one POST to `/REST/2.0/ticket`. It reads back ID, queue, generated subject and merge identity before exposing a verified ticket link.

Run a worker with deployment credentials loaded:

```sh
uv run python manage.py process_rt_tickets --all --due
```

The bundled worker includes this command. Repeated/concurrent workers do not create duplicate POSTs. An uncertain creation is reconciled using bounded read-only search for the exact queue/subject; no blind POST retry. Remote URLs in API responses are ignored. Status/owner/due-date refresh is separate workflow feedback; completion never patches inventory, changes applicability or closes an issue. Access/transport failure retains the last known state. Revoked visibility suppresses read access and further hand-off.

HTTPS verification, bounded JSON, timeouts and redirect refusal apply. RTIR-specific creation, deployed queue scrips, production service accounts, remote retention and live permission tests remain installation acceptance work.
