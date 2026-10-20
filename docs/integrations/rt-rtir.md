# Optional RT / RTIR hand-off

Status: **planned; no connector or deployed-version compatibility validated**. The owner requested optional integration with [Best Practical RT/RTIR](https://bestpractical.com/). See the [agreed phases](../roadmap.md).

Treat RT/RTIR as an optional response workflow destination. Bearings retains asset/source identities, applicability, lifecycle facts, risk context, sharing rules, stakeholder selection and notification approval. RT/RTIR retains queue workflow, ownership and ticket history. FlowIntel remains available; users choose the destination and explicitly link any additional ticket instead of implicitly creating both.

Verify the actual deployed RT/RTIR release, enabled API (REST2 is a candidate, not a certified contract here), authentication, queue/type/custom-field requirements, creation/read permissions, TLS and operator-approved source scope before implementing a client. RTIR-specific Investigation/Incident/Report/Countermeasure terminology and relationships need validation against that deployment. Classify CVE/lifecycle/exposure work deliberately; an expiring warranty alone is not an incident.

First bounded pilot: one scoped issue, exact destination/export preview, creator approval, private/appropriate queue access, stable source-bound ticket identity, committed pre-I/O claim, safe read-only reconciliation after uncertain creation, manual/scheduled read-back of status/owner/due date and retained last-known state on failure. Keep keys server-side. Completion must never automatically close an issue or establish that an asset is patched. Verify unrelated-company/reader denial, revoked sharing, repeated/concurrent requests and lost acknowledgments with synthetic records before live operation.
