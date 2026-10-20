# ADR 0007: Reviewable notification batches and local file outbox

Accepted 2026-10-20.

CIRCL needs bulk outreach for registered installations, while organizations need an internal notification and acknowledgment workflow. Existing finding visibility is necessary but insufficient: an operator may investigate evidence it cannot redistribute. Product names do not establish affectedness, and a sent email does not establish remediation.

Use current active findings as the candidate source, with product/CVE/source-severity/assessment/organization filters and deterministic global ordering. CIRCL outreach requires explicit operator visibility; company campaigns require organization edit membership. Both require shareable evidence. Organization administrators explicitly include contacts and must have email reachability and a current role review; availability is separate. Do not silently omit organizations with missing eligible recipients.

Store batches, rendered per-contact previews, protected finding links, content fingerprints and audited approval/acknowledgment. Revalidate current authorization, eligibility and preview content before approval and again before I/O. A unique receipt is committed before local file output; crashes remain visible as uncertain attempts and are not automatically retried. Separate database/file operations cannot promise exactly-once delivery. Protected relationships preserve the evidence reference until explicit retention governance exists.

Restrict Django template rendering to a documented flat text context. Reject template tags, comments, arbitrary variables, filters and attribute traversal; supply no model objects, request or loaders. Escape previews in HTML. Use an explicit file mail backend independently of global mail transport settings.

This delivers preparation, local approval, an inbox and acknowledgment. It does not deliver automatic source subscriptions, product/version affectedness, production transport, remote delivery/read confirmation, remediation, reminders or escalation. Preserve those as explicit follow-up work.
