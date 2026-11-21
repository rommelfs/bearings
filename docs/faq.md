# Frequently asked questions

Reviewed 2026-11-20. This FAQ describes implemented development/pilot behavior, not production acceptance.

## What is Bearings?

Bearings connects a company's infrastructure inventory with vulnerability evidence, business risk, accountable contacts and follow-up. It gives company teams a view of what needs attention and gives authorized CIRCL analysts a view across participating organizations.

## Who operates the Bearings service?

This Bearings installation is operated by CIRCL. CIRCL is Luxembourg’s CERT for the private sector and municipalities. The Law of 5 May 2026 implementing NIS2 designates CIRCL as a CSIRT; Article 9 names CIRCL as the coordinator for coordinated vulnerability disclosure. We scan for vulnerabilities and support voluntary information sharing so organizations can act earlier.

## Is Bearings free to use?

Yes. The CIRCL-operated Bearings service is free and will remain free, including continued use after registration. Start with a responsible contact and one domain or network, then add details over time. Colleagues can join by invitation. Optional external tools have their own account and operating requirements.

## Do I need a complete inventory to get started?

No. Start with a responsible contact and one domain, IP address or network. Add hardware, software and versions over time. A resumable setup guide and individual editors let you continue later. Unknown or missing data remains visible as a coverage gap.

## How do I join my existing company?

Ask your company administrator for an email invitation. Accept its one-use code with your existing account, or create your own account if you do not have one. The first registrant of a new company becomes its administrator. Administrators can invite administrators, editors and readers; this never grants CIRCL or platform privileges.

## When does the company get access, and when does CIRCL?

Email confirmation opens the private company workspace. CIRCL reviews sharing separately. Declared IPs and domains remain declarations until their responsibility is reviewed. Email possession, company membership and infrastructure authority are separate facts.

## Can we reuse NetBox or import a spreadsheet?

Yes. Operator-approved NetBox connections import devices, VMs, IPs and prefixes. A manually maintained inventory supports reviewed CSV imports up to 500 rows / 1 MB. Each company has one authoritative inventory source. A CSV upload does not write to NetBox; software/version details are separate from basic network discovery.

## Does a CVE match mean a server needs a patch?

A match starts a review. A product name or a high CVSS score alone does not prove that a particular installation is affected. Review the version, exposure and evidence, assign responsibility, and record the tested action. Bearings does not install patches or infer successful remediation from an empty issue list.

## How does Bearings support risk analysis?

Vulnerability evidence can be linked to public MOSP/MONARC scenario definitions and company-specific consequences, treatment and review decisions. Automatic scenario drafts support human review. Source severity, local qualitative risk and a full native MONARC assessment remain distinct; a scenario suggestion is not a confirmed business impact.

## Can analysts research an affected version before a CVE exists?

Yes. Authorized CIRCL analysts can search participating companies' recorded software/version inventory without a CVE. Findings are research leads limited by inventory freshness, exact recorded facts and current access. A restricted report does not automatically become a company notice or a finding.

## Does National Overview describe all of Luxembourg?

It describes currently permitted, participating inventory: outstanding reviews, software-version prevalence, recorded activity and company locations. It does not claim complete national coverage, verified patch installation or a predictive security score. The map shows company locations, which may differ from server locations.

## Whose MISP permissions does a customer use?

Their own. Optional personal connections use the customer's read-only MISP key and isolated cache at an approved server. CIRCL's universal key is reserved for internal research and is never a customer fallback. Colleagues do not inherit personal caches. Default refresh/expiry is 5/10 minutes; the current pilot is bounded to 500 events / 20 MB.

## Is Bearings directly connected to AIL?

No. Companies can supply optional keywords, separate Honeytoken indicators and a team notification mailbox. Bearings exports a configuration for manual import into AIL. Analysts review results and choose whether to notify through Bearings or AIL. There is no automatic AIL feed or unreviewed alert stream.

## How do data reviews and the email reaction test work?

The service emails responsible people to review their contacts and inventory and confirm a snapshot through a link. Platform administrators set the review schedule; CIRCL analysts can also manage it for approved companies. Registered companies cannot disable required review emails. Message preparation, delivery and an actual response remain separate evidence: a sent message alone does not count as confirmation.

## Can a security team or DPO be included?

A separate team mailbox can be supplied, for example security@, abuse@ or noc@. Notification eligibility depends on mailbox/role review and the selected workflow. DPO inclusion is an optional reviewed audience choice, not an automatic escalation on every vulnerability. Emergency telephone details are collected separately.

## Is SSO available across the ecosystem?

Your company uses its Bearings account to access the CIRCL-operated workspace. Optional single sign-on depends on the login methods enabled by the operator. Connected applications keep their own permissions; a company invitation does not automatically grant access to MISP, NetBox or incident-coordination tools.

## What happens if a company is registered twice or companies merge?

A platform administrator can review a company merge. Members of the original company join the target; users already in both companies retain their target role. Supported local manual inventory and evidence are transferred together, and the original company is archived. Native identities, external source bindings and conflicting data require separate reconciliation. Similar company names never automatically grant membership or trigger a merge.

## Is Bearings ready for production?

Bearings is a development and pilot project with automated tests and synthetic reference deployments. Tests with 40,000 companies and 1.2 million assets passed within the documented resource and workload limits. This is not a production approval: sustained testing on the intended deployment, real-service permissions and versions, operational email delivery, monitored jobs, backup/restore, retention and native-account revocation still require validation.

## Is Bearings open source, and does this website show real company data?

The software is licensed under AGPL-3.0-or-later. Infrastructure and intelligence data retain their own access and redistribution rules. Every product image on this website uses synthetic example data. The website is static, has no application login, visitor analytics or advertising cookies, and does not connect to private CIRCL services.

## Do we need a Linux client, and what does it do?

The client is optional. It keeps Linux package versions current in the CIRCL service and can be deployed with a limited rollout code. Each machine uses its own signing key and HTTPS. Supported distribution CVE checks run in Bearings; the client does not patch your systems. Managed NetBox registration is available when enabled by the operator. CSV and existing NetBox connections remain available.

See the [documentation index](README.md), [next steps](product/next-priorities.md) and [validation record](validation.md).

Content source: `website/faq.json`; rebuild with `python3 website/build.py`. The tracking/privacy statement applies to the public static website, not to authentication or logs in a deployed Bearings application.
