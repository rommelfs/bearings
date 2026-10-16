# Incident handling

For suspected application compromise: restrict service access through the operator deployment layer, stop job processes you own, preserve database/audit evidence and logs with access controls, and coordinate through a verified secure channel. Do not publish company details in GitHub issues. Review operator policy/membership changes and sensitive-access audit events. Rotate affected credentials in their source systems/secret store, then revalidate scoped operations. Avoid logging tokens or raw restricted intelligence during diagnosis.

For stale/failed connectors: retain last-known data, mark the affected coverage unavailable, inspect safe health/status and upstream access, correct approved configuration, retry and verify external identity. An outage is not proof the inventory is empty or safe. Do not enable scanning or production notification delivery as an incident workaround without authorization.

For a finding: distinguish evidence reference, potential applicability, exploitation elsewhere and confirmed organization-specific compromise. Record analyst reasoning and workflow separately; preserve original evidence. Notifications must respect source restrictions even in summaries. Current delivery is a local file sink only. Production escalation/response ownership, contact channels and SLAs remain open decisions.
