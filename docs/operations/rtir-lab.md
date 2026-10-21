# Native RTIR coordination lab

Bearings optionally installs **Best Practical RTIR 5.0.10** on its security-patched Debian RT 5.0.7 reference. These versions are compatible with RTIR's supported RT 5.0.x series. This is the actual extension, native queues, custom fields, scrips and lifecycles, not renamed RT tickets. RTIR source is fetched from [Best Practical](https://download.bestpractical.com/pub/rt/release/RT-IR-5.0.10.tar.gz) with pinned SHA-256 `b99d35e5e7730ce1ac99719b995a5e6756993986b3f90b8748867a9e68fcbd55`. The image retains the original GPLv2 source archive and upstream notices separately from Bearings' AGPL license. Parse::BooleanLogic 0.10 is also digest-pinned.

```sh
git pull
python3 scripts/dev.py up --sso --flowintel --rtir
python3 scripts/dev.py trust
python3 scripts/dev.py credentials
python3 scripts/dev.py manage seed_rtir_example --bundled
python3 scripts/dev.py sso-smoke
python3 scripts/dev.py smoke
```

`--rtir` implies `--rt`. FlowIntel and SSO are optional. Later `up` calls remember the profile. Bearings: <http://127.0.0.1:8000/>. RTIR uses the same verified HTTPS RT entrance at <https://localhost:9445/RTIR/>; emergency local root recovery remains <https://localhost:9446/>. Use `circl-analyst` for RTIR and Bearings coordination. The company account retains its ordinary company RT queue and has **no RTIR queue or ticket access**.

## From risk to response

1. As the CIRCL analyst, open an **Asset issue**, then its RT/RTIR hand-off. Select `bundled-rtir-circl`, give the reason for escalation and leave **Incident** blank. Review the exact evidence export and explicitly approve. The worker creates one native ticket in **Incidents**.
2. Open each relevant asset issue, select the same connection and choose the verified Incident in the **Incident** field. Review and approve each Investigation separately. The worker creates tickets in **Investigations** with native `MemberOf` links to that Incident in the original creation request.
3. **RTIR coordination** in Bearings lists visible Incidents. An Incident detail shows its Bearings-managed Investigations, company, asset, issue and last verified lifecycle status. Links lead to the asset evidence, Investigation preview and actual RTIR ticket. The same Incident can coordinate issues across multiple explicitly operator-visible companies. Currently one Investigation per connection/asset issue is retained; use distinct issue records for distinct questions. An existing binding cannot be silently moved to another Incident.
4. Work the native lifecycles in RTIR. Bearings refreshes verified status/owner/due through GET. A resolved Investigation or Incident does not change applicability, issue assessment, inventory or remediation evidence. New vulnerabilities and other risks do not automatically become confirmed incidents.

The optional example command creates/reuses one clearly synthetic Incident and three Investigations for three bundled NetBox assets across two companies. It is a live local connector exercise, not an operational incident. Startup alone does not export issues. `smoke` includes this same repeatable proof, native lifecycle/parent verification, separate token denial and read-only recovery after a simulated lost local acknowledgment. Unit tests additionally cover multiple-company visibility withdrawal, source/parent changes and export authorization.

## Permission and retention boundaries

The dedicated `RT_BUNDLED_RTIR_TOKEN` bridge is separate from both ordinary RT bridges. It can create/read the two coordination queues and has the native `ModifyTicket` right needed for linking. The connector itself allows only ticket creation and bounded GET/search, with exact queue, subject, effective ID, lifecycle and parent verification; it cannot send arbitrary status/comment/link updates. The CIRCL human receives explicit queue rights; neither company users nor ordinary API bridges enter RTIR or DutyTeam. The initial upstream Everyone submission/reply grants on the four new RTIR queues are removed **once**, during first installation. Operator changes after completed installation are retained, not regranted on restart.

Bearings keeps Incident aggregates CIRCL-only. If any linked company's current visibility is withdrawn, the whole aggregate and its Investigations are hidden from that analyst and further exports/refreshes are blocked. This does not remove material already exported to RTIR; its independent retention and user-access policy still applies. Companies continue to receive individually approved information through their Bearings workspace/notification workflow. There is no shared company-facing RTIR dashboard or automatic bulk notification from an Incident.

The lab retains the existing RT database, tickets, queues, users, secrets, policies and SSO client. First RTIR installation refuses conflicting native queue names. It inserts official RTIR initial data once, then stores the exact queue identities/version. Interrupted insertion fails closed for explicit private recovery; it does not blindly run initial data again. After successful insertion, a retained provisioning stage can complete without reinsertion. Completed setup preserves revoked grants, disabled accounts/connections and keys. Missing or changed retained identities/keys require recovery, not automatic replacement.

Once RTIR is installed, its plugin remains loaded with that retained database, including when the ordinary RT profile is used later. `up --no-rt` stops the optional backend while retaining its data and RTIR selection; `up --rt` restores it. Do not delete volumes or downgrade an installed RTIR database to remove an optional UI. This increment does not implement RTIR version upgrades or arbitrary pre-existing queue adoption.

RTIR shares the [RT lab](rt-lab.md) isolated network, local-only mbox mail, verified TLS, explicit SSO identities and independent local recovery. No SMTP, remote scan, production case or external account is provisioned. Independently operated RTIR deployments require explicit queue/lifecycle/ACL/scrip/custom-field acceptance; production mail and customer-facing RTIR access remain separate work.

A failed native queue/parent preflight before any POST leaves a blocked preview that can be reviewed and approved again. Once a POST may have reached RTIR, the outcome remains uncertain until GET-only reconciliation; no automatic POST retry is made.
