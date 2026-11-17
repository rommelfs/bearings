# Infrastructure overview and automatic product setup

After signing in, Bearings opens **Infrastructure overview** (`/`). Company users see their permitted companies; CIRCL analysts see companies allowed by current operator visibility or ordinary memberships. The brand link and the first navigation item return here. **Vulnerability review** remains available at `/reviews/` with its existing evidence, severity filters and assessment workflow.

## Read the company state

Each company card separates active inventory, confirmed affected reviews, overdue actions and monitoring coverage:

- **Action required:** a recorded confirmed-affected review, an overdue active issue action or an expired risk acceptance needs attention.
- **Review required:** open CVE/lifecycle issues exist, but confirmed affectedness or overdue action is not established.
- **Coverage incomplete:** no active inventory, stale/missing source data, missing software/versions, unknown product mappings, explicitly paused/stale product watches, retained missing assets or unavailable response contacts prevent a complete view.
- **No open items recorded:** no currently visible actionable items or recorded coverage gaps were found. This is not proof of safety, complete inventory, successful patching or absence of unknown vulnerabilities.

Coverage gaps remain visible even when the main state is Action/Review required. CVE source severity and unknown source severity are shown separately from analyst affectedness and company business risk. Synthetic inventory is labeled. Watch freshness means a complete supported read within the configured interval; it does not establish version applicability. The oldest successful refresh date covers reporting watches only; watches that have never succeeded are listed as gaps.

Use **Servers needing attention** to reach the prioritized asset list: overdue actions first, followed by confirmed affectedness, high-priority lifecycle/exposure issues and critical source reviews. Server names, recorded IP/DNS, contact/team and existing next actions link to the actual asset/software details. A product/CVE match creates investigation work; it does not automatically prove that a particular update is needed. Exact fixed-version/build/backport recommendations remain outside this bounded increment.

**Auto-refresh every 60 seconds** starts checked. It reloads the current view only while the tab is visible and no text/select field is being edited. Uncheck it to stop page refresh for that page. This page refresh reads local state; background source refresh is a separate worker operation. Company search, selection and pagination remain in the current URL. Overview reads never enroll products or contact upstream services.

## Known products: monitoring without typing catalog keys

New installed software is considered for automatic monitoring immediately. Bundled initialization and `sync_vulnerabilities` also enroll existing installed products that have no watch. The watch starts **enabled**, queued for its first complete read, with a default 60-minute source interval (minimum 15). Existing custom mappings, pinned source identities and explicitly paused watches are preserved.

Local suggestions come from:

1. Concrete unescaped CPE 2.3 vendor/product identity (`a`, `o` or `h`, with concrete vendor/product values).
2. Supported exact package identities: Log4j Maven `log4j-core` and `log4j-api`, including their versioned PURLs.
3. An exact known-name alias: Apache Log4j/Log4j → `apache/log4j`; Microsoft Exchange Server/Microsoft Exchange → `microsoft/exchange_server`; Fortinet FortiOS/FortiOS → `fortinet/fortios`. Name comparison ignores case and repeated whitespace, not arbitrary suffixes or similar words.

These aliases were checked against the public catalog. They establish a mapping candidate, not confirmed affectedness. Demo identifiers such as `demo:product:0` are not normalized identifiers, but an exact recognized product name can supply the mapping. Conflicting concrete identifier/name candidates remain a visible setup gap and require choosing the right identity. Unknown products are never silently guessed.

Opening **Configure automatic CVE discovery** shows known candidates already filled in and Enabled checked for new watches. A form GET makes no upstream call or saved change. Automatically enrolled watches show their saved mapping. Updates to the exact version/build queue another evaluation; no endpoint scanner is installed and software is not inferred from a server name.

## Unknown products: select from the public catalog

1. Open **Installed software → Configure automatic CVE discovery**, or **Automatic CVE discovery → Configure product watch**.
2. Enter the public manufacturer name in **Search term**, then choose **Find manufacturer**. Select the correct result.
3. Enter a product term and choose **Find product for selected manufacturer**. Select the exact product identity.
4. Check the selected keys and interval, leave Enabled checked and **Save**. Background refresh starts from the queued watch.

Search does not submit the watch form or change its fields before a result is selected. Existing interval/other entries remain intact while browsing. Manufacturer selection explicitly clears an older product key; product selection fills both keys. Failed searches and late responses do not replace entered data. Without JavaScript, the key fields and Save remain available for manual configuration.

The picker sends only the search terms you enter and the selected public manufacturer to the approved source. Company/asset names, installed versions, IPs, contacts and risk assessments are not transmitted. Each search retrieves one bounded page of up to 20 catalog entries, with at most 100 accessible pages; refine broad searches. Source links are not followed. Existing saved sources remain pinned. A source outage or incompatible response shows a failure and preserves the form; it never fabricates a mapping.

## Start/update

On the feature branch until it is merged:

```sh
git pull
python3 scripts/dev.py up
```

The starter applies migrations as usual, locally enrolls recognized existing software and starts the worker. No new schema migration is required by this follow-up. Native setups must schedule `sync_vulnerabilities --due` in addition to their existing inventory and notification jobs; it also enrolls recognized existing software. Initialization creates local watches only; subsequent source operations are bounded GETs. No production message, scan, public deployment or external inventory write is enabled.

## Browser examples

Screenshots use a fictional company, real public CVE/catalog reads and synthetic action/contact context. They are separate from the bundled dataset.

![Company infrastructure state and prioritized actions](../images/infrastructure-overview.png)

![Known product prefilled with auto-refresh enabled](../images/product-prefill.png)

![Public catalog selection without memorizing product keys](../images/product-catalog-search.png)

## Open the actual problems and suggested risk scenario

Every server card now includes linked problem titles, their dates and individual next actions. Identical action text remains attached to distinct named problems. Overdue badges filter **action deadlines** exactly; expiry/EOL dates remain separate. CVE/confirmed/critical counters open the scoped vulnerability queue; lifecycle counters open the scoped issue list. All-problem links use an exact asset ID, not a potentially ambiguous server-name search. Asset/attention filters survive subsequent filtering and pagination.

Each issue also receives an automatic conditional risk-scenario draft derived from current source weakness/text or issue type. Follow its link to review compatible cached MONARC scenarios, preview a selected template and confirm a prefilled justification with pinned evidence. This prepares business consequences and treatment context without guessing likelihood/impact or accepting company risk. [Workflow and boundaries](automatic-scenarios.md).
