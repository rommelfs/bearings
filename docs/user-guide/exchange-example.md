# Unpatched Exchange: what an analyst sees

This is an explicit **synthetic exercise**, with real public vulnerability and catalog evidence. It is not a real company's inventory, a vulnerability scan, or evidence of exploitation.

## Verified source facts and exercise assumptions

On 2026-10-19, both [Vulnerability-Lookup](https://vulnerability.circl.lu/api/vulnerability/CVE-2026-70571) and the [CVE Program record](https://cveawg.mitre.org/api/cve/CVE-2026-70571) published Microsoft's **Exchange Server Remote Code Execution Vulnerability**. The CNA describes stack-based buffer overflow allowing an unauthorized attacker to execute code over a network. Its CVSS 3.1 base score is **8.1 / High**, vector `AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:H/A:H`; high attack complexity matters. This does not establish active exploitation. See the [Microsoft advisory](https://msrc.microsoft.com/update-guide/vulnerability/CVE-2026-70571) for current edition-specific remediation.

The exercise assumes **Exchange Server 2019 CU15, build 15.2.1748.54**. Microsoft's CVE record lists this edition's builds below **15.02.1748.055** as affected. This is an explicit manual comparison of the assumed edition/build, not an automatic version matcher. Other supported/affected editions have different thresholds. Do not apply the CU15 threshold to CU14, 2016 or Subscription Edition.

The example server is business-critical by exercise choice. Network reachability and absent patching are assumptions, not tested observations. No address is probed, no Exchange server is installed, and no exploit is run. Only an inventory object and software/build record are created.

## Add the example

For the bundled development environment, after updating the checkout:

```sh
python3 scripts/dev.py up
python3 scripts/dev.py example-exchange
```

If you already ran `python3 scripts/dev.py manage seed_exchange_example --bundled`, the case exists but its network/location fixture has not been populated. Complete that existing case without another CVE/MOSP lookup:

```sh
python3 scripts/dev.py example-exchange --inventory-only
```

This fills real bundled NetBox primary IPv4 `192.0.2.25/24`, IPv6 `2001:db8::25/64`, DNS `exchange-01.mail.example.invalid`, Luxembourg DC / Messaging room M1 / rack EX-01 / U22 / front, then imports them into Bearings. The lower-level `manage seed_exchange_example --bundled` command only records the case and evidence; running it again does not execute this placement step. Use the complete helper above for new examples.

The command adds `exchange-example-01 (SYNTHETIC)` to the existing bundled **writable** organization's tenant using its scoped NetBox connection. It confirms the inventory write before creating a finding. It refuses external mode, altered lab identities, disabled/read-only targets or actors without editing rights. It never changes access mode or grants itself remote permissions. The separate bundled read-only company is untouched.

It retrieves the live CVE, verifies the expected published edition/range, and pins a live CC0 MOSP **Server / Malware infection / Update management (patches) is flawed** scenario (`7f9fc1a8-4f02-11e9-b3ea-0800277f0571`). The link's reason explains that a deliberately unpatched server warrants reviewing patch management; it does not prove an organization-wide process weakness.

For native Django development, initialize existing demo accounts first, then run:

```sh
DJANGO_DEBUG=1 uv run python manage.py seed_exchange_example
```

Native mode uses a separate **Exchange Company (SYNTHETIC)** workspace (`exchange-example`) and the clearly labeled development inventory adapter; it does not claim a NetBox origin. `--actor <existing-active-editor>` selects a different existing account. No default password or privilege elevation is added. Public connector DNS/proxy/TLS requirements apply in both modes; see [MOSP setup](../integrations/mosp.md). Docker build-time proxy configuration does not provide runtime public API connectivity.

Repeating the command reuses its inventory identity and finding, refreshes CVE evidence while preserving operator restrictions, and leaves analyst decisions, history and withdrawn mappings intact. It refuses to downgrade a changed build or revive a retired asset. Public API failures are explicit; a MOSP outage can leave a valid Exchange finding pending its catalog mapping. Retry to complete it. No fabricated replacement CVE is inserted.

## Analyst workflow

Sign in as `circl-analyst` and open the start page. The **Needs analyst review** queue includes the example when its organization permits CIRCL visibility. It displays:

- `CVE-2026-70571`, the Exchange RCE title and source severity **High / CVSS 3.1 8.1**;
- organization, asset, product/build, asset criticality and responsible team;
- **under_review**, with **manual analyst applicability: affected** and an explanation explicitly marked synthetic;
- a direct link to that finding in **Asset → Vulnerability → Risk**, with current and pinned evidence and the MONARC scenario.

The manual assessment is recorded once with the example actor and reason in finding history. Automated applicability stays **unknown**, no compromise is asserted and business risk remains **unassessed**. The start-page queue shows active `new`, `under_review` and `confirmed` findings, with high-criticality assets first, then recent evaluation. It does not sort by an inferred risk score. Closed/accepted-risk records remain in their workspaces; acceptance does not imply a patch or safety. Queue counts, pages, descriptions and direct links all obey current organization and evidence visibility. Restricted source data and derived cues are not disclosed to participants.

Source titles and CVSS summaries are now displayed for other supported CVE JSON records too, not only this example. Missing/unsupported severity stays unknown. Source text is escaped. CVSS severity is not an organization's impact/likelihood assessment.

## Consequences and actions

If exploitation succeeds, review these possible consequences in the organization's actual context:

| Possible consequence | What must be established locally |
| --- | --- |
| Confidential email/data exposure | Process privileges, accessible mailboxes/data, sensitive content and logging |
| Message or server-data manipulation | Permissions, integrity controls and possible business fraud paths |
| Mail-service outage | Operational dependency, recovery time, backup and alternative communications |
| Follow-on compromise | Credentials available to the process, segmentation and reachable systems |

None of these are observed incidents in the exercise. The recorded explanation describes them as possibilities. Next verify the actual edition/build and reachability, install the current vendor update appropriate to that edition, verify remediation and update the local software/build and analyst workflow. Investigate compromise separately if indicators warrant it. A patch does not by itself prove the server was never compromised.

The MONARC link remains a review hypothesis. Risk owner, likelihood, business impact, treatment, deadlines and formal acceptance are still separate future assessment capabilities.

## Does Bearings alert automatically?

**In-app: yes, after the CVE review is recorded.** The start page surfaces active visible findings without requiring an analyst to visit every organization. The example supplies its explicitly manual assessment and context.

**Automatic discovery from NetBox import: no.** Inventory alone does not establish installed Exchange versions or applicable CVEs. Continuous product/version matching and automatic CVE discovery remain backlog work. The example command is not a general matching engine or scanner.

**Outgoing email, pager, push alerts or escalation: no.** This change sends none. Production notification delivery requires a separate implementation and operational authorization. The existing local contact-review mail sink is unrelated to vulnerability alerts.

## Locate the actual example asset

The [asset triage guide](asset-triage.md) describes the new severity cards, search/filters, linked asset details and the guarded `python3 scripts/dev.py example-exchange` helper. For an already seeded example, `example-exchange --inventory-only` adds verified synthetic NetBox IP/DNS/datacenter/rack context without another public CVE lookup. Source severity now sorts before asset criticality; the earlier criticality-only ordering has been superseded.

The optional [FlowIntel workflow](flowintel.md) adds a reviewed private case, follow-up tasks and status feedback for the existing finding. It does not resolve findings or send notifications automatically.
