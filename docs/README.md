# Bearings documentation

Reviewed 19 November 2026. Bearings is a runnable development/pilot workspace; passing local tests does not establish production acceptance. Guides describe implemented workflows; the validation record distinguishes synthetic fixtures, bundled native services and untested external deployments.

## Start here

- [Frequently asked questions](faq.md): access, company membership, inventory, CVEs, MISP, AIL, mail, SSO and current limits.
- [Company first steps](user-guide/company-first-steps.md): minimal useful setup, reviewed CSV import and concrete actions.
- [Company membership](user-guide/company-members.md): invitations, roles and reviewed organization merges.
- [Registration](user-guide/reporting-registration.md) and [resumable company configuration](user-guide/company-configuration.md).
- [Linux installer and roll-outs](integrations/linux-rollout.md): central downloads, clipboard/stdin registration and automation boundaries.
- [Linux inventory client](integrations/linux-agent.md): authenticated patch observations, explicit first-host registration and safe source ownership.
- [Current project steps and priorities](product/next-priorities.md): implemented increments and the next acceptance gates.

## Choose your workflow

| Audience / task | Guides |
| --- | --- |
| Company infrastructure owner | [Infrastructure overview](user-guide/infrastructure-overview.md), [asset issues](user-guide/asset-issues.md), [risk scenarios](user-guide/risk-scenarios.md), [continuous review](user-guide/continuous-review.md) |
| Company account and contacts | [Members](user-guide/company-members.md), [registration](user-guide/reporting-registration.md), [SSO](user-guide/company-sso.md), [infrastructure verification](user-guide/infrastructure-verification.md) |
| CIRCL analyst | [National overview](user-guide/circl-overview.md), [Luxembourg map](user-guide/circl-map.md), [review follow-through](user-guide/review-followups.md), [notifications](user-guide/notifications.md) |
| Personal intelligence and monitoring | [Personal MISP](user-guide/personal-misp.md), [MISP contract](integrations/misp.md), [AIL configuration/export](user-guide/company-configuration.md) |
| Platform operator | [Administration](user-guide/platform-administration.md), [development stack](operations/development-stack.md), [deployment](operations/deployment.md), [backup/restore](operations/backup-restore.md), [SSO operation](operations/sso.md) |
| Integrator / developer | [Architecture](architecture.md), [authorization](authorization.md), [data model](data-model.md), [NetBox](integrations/netbox.md), [Vulnerability-Lookup](integrations/vulnerability-lookup.md), [MOSP](integrations/mosp.md), [federation](integrations/federation.md) |
| Evaluate the project | [Validation evidence](validation.md), [40,000-company baseline](performance/scale-test.md), [measured scale improvements](performance/scale-improvements.md), [historical roadmap](roadmap.md), [current priorities](product/next-priorities.md), [backlog](backlog.md), [license](licensing.md) |

## Project website — local preview

The English/German/French/Luxembourgish static website source is in [`website/`](../website/README.md). It contains use cases, synthetic screenshots and the FAQ. It is an information website, separate from the authenticated application. It remains local-only at the owner’s request; free-registration buttons point to the local lab. All four languages include source-backed real CVE examples with clearly fictional humorous quotes. See [example/source review](product/website-examples.md).

## Documentation maintenance

The FAQ's single content source is [`website/faq.json`](../website/faq.json); `python3 website/build.py` generates the static pages and `docs/faq.md`. Keep implemented behavior, development defaults, deployment-specific acceptance and planned capabilities distinct. Product screenshots are illustrative synthetic examples, not live national/company statistics.

This pass reconciled outdated summary claims in the README, authorization, architecture, data model and priorities and added navigation/FAQ. It was not a claim to have independently revalidated every deployed integration or every historical entry in the validation record. Update the corresponding guide and validation evidence whenever behavior changes; check the static website/FAQ before republishing. See the [website maintenance guide](../website/README.md) for the reproducible build, preview, public-source branch and release checklist.
