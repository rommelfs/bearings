# Configurable local application version profiles

The Linux client supplements Debian/RPM package inventory with bounded application
observations. Profiles are local administrator/collector-controlled JSON, not
commands supplied through the web application. They run during the ordinary
`--inventory` capture, including the default six-hour watcher. Package coverage
and application observations remain separate: a complete package database is not
complete application discovery or runtime attestation.

MISP is a built-in profile, not a separate hard-coded transport. Without a local
configuration file the client checks readable, non-symlink `VERSION.json` files
at `/var/www/MISP`, `/var/www/misp`, `/opt/MISP` and `/opt/misp`. The official MISP
2.5 branch's `VERSION.json` was independently read on 2026-11-21 and contains
integer `major`, `minor`, `hotfix` fields. No PHP or application code is executed.

## Local configuration

Use `/etc/bearings-linux/application-probes.json`. A supplied file replaces the
built-in list; include MISP explicitly if you still want it. An empty list
intentionally disables application collection. The file must be root/collector
owned, not shared-writable and reachable without symlinks through trusted parents.
Deploy it with an existing configuration-management tool such as Ansible. There
is no web-to-agent command channel or centralized profile editor in this release.
The [example configuration](../../clients/linux/examples/applications.json)
contains illustrative paths: review and adapt them before deployment.

```json
{
  "schema": "bearings.application-probes.v1",
  "applications": [
    {
      "id": "misp-main",
      "method": "json-fields",
      "name": "MISP",
      "identifier": "cpe:2.3:a:misp:misp:*:*:*:*:*:*:*:*",
      "path": "/var/www/MISP/VERSION.json",
      "fields": ["major", "minor", "hotfix"],
      "version_pattern": "^([0-9]+\\.[0-9]+\\.[0-9]+)$"
    }
  ]
}
```

| Method | Input | Version extraction |
| --- | --- | --- |
| `misp-version-json` | MISP `VERSION.json` | Fixed integer major/minor/hotfix schema; name/CPE are known. Only `id`, `method`, `path` are needed. |
| `json-fields` | A local JSON release manifest | `fields` contains 1–8 dot-separated object paths. Scalar values are joined with a dot, then normalized with `version_pattern`. |
| `file-regex` | A local text release file | A Go/RE2 regex finds exactly one match with exactly one captured version. Use `(?m)` for line anchors when needed. |
| `git-tag` | A local repository with a real `.git` directory | Fixed Git queries read HEAD, tags pointing directly at HEAD and tracked working-tree status; the pattern must identify exactly one release version. |

Generic methods require `name`, `path`, `version_pattern`; `identifier` is an
optional explicit product CPE or package URL. Use the correct public product
identity to enable known vendor/product CVE monitoring. A generic name/identifier
alone does not prove applicability. Unknown identities remain inventory with a
monitoring coverage gap; the client does not guess a vendor from arbitrary file
contents. Without an explicit identifier, the local generic product identity
uses name/profile ID and is stable across devices in that organization.

Regexes use Go/RE2, with one capture group and at most 512 characters. They are
not arbitrary code or a shell. Missing/multiple captures, invalid output,
ambiguous JSON keys or unknown methods are errors. Keep profile IDs and paths
stable; changing an already bound program's path/method/product identity requires
releasing its version ownership. At most 16 unique profiles/paths are accepted.
Custom executable version queries remain in the separately reviewed
[`binary-probes` profile](../../clients/linux/README.md#manually-installed-native-binaries),
with fixed arguments, executable fingerprints and a separate partial scope.

## Git semantics and limits

`git-tag` invokes only the trusted `/usr/bin/git` as the unprivileged collector.
It uses fixed argument lists, not configurable shell fragments. Git global/system
configuration and inherited credentials are not used; pager, hooks, fsmonitor,
maintenance, submodule inspection, lazy/network fetching and optional index
writes are disabled. Each command has a four-second deadline with process-group
cleanup; profiles share a 30-second scheduling budget. It never runs `fetch`,
`pull`, `checkout`, build tools or application code.

A commit hash is stored separately and never substituted for a release version.
No exact matching tag, multiple matching tags, a changed HEAD, a Git error or
modified tracked files withholds a release observation. Git worktree redirects,
symlinked paths and root execution of this method are unsupported. Git reports
tracked-file changes only; untracked/ignored content, submodule contents and the
version actually served by a running process remain outside this assertion.

## Evidence, permissions and failure handling

File reads walk paths through directory descriptors without following symlinks,
reject special files and bound content to 64 KiB (4 KiB for the fixed MISP schema).
The reader checks file identity/metadata before and after reading. The report
contains only the normalized version, local path, method and SHA-256 evidence
fingerprint; generic profiles also include a profile fingerprint, with commit
and tracked-clean status for Git. Whole source/configuration files, arbitrary
Git output and probe regexes are not sent. Choose non-secret release metadata;
profile authors must not capture credentials into a version field.

The collector's existing permissions are retained. It does not become root or
join the web application's group. If an application tree is not traversable,
an administrator can grant execute-only access to its parent directories and
read-only access to the specific public release file, for example with a
reviewed ACL. Do not grant access to MISP database/API configuration just to read
`VERSION.json`. A safe local check is:

```sh
runuser -u bearings-linux -- /usr/local/bin/bearings-linux collect --inventory \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("applications", []))'
```

This command collects locally without uploading. Errors appear on stderr and
retain earlier observations; package inventory is still collected. Missing,
malformed, unreadable or ambiguous application metadata does not erase software,
assert removal, refresh the previous component timestamp or resolve CVE reviews.
Application observations become stale independently after the existing 12-hour
window. Probe failure details currently live in the client service journal,
not a separate server-side failure report. Restarting the service triggers its
normal jittered capture, not an immediate synchronous successful upload.

## Automatic inventory and existing software

The signed `bearings.agent.v1` report has an optional `applications` array,
independent of package `components`. Existing clients remain accepted; upgrade
the server first. The receiver checks approved methods, bounded identities and
metadata and keeps application coverage partial. New observations create
separate software installations only while the device's automatic software
policy is enabled, then queue known product monitoring. Future reports update
only the owned version field and queue reevaluation; they preserve edition,
build, paused watches, analyst decisions and workflow.

Existing manual/CSV installations are never silently adopted. In **Linux clients
→ observations**, find the application and use **Link this application to existing
software → Assign version ownership** once. Only a matching product on that host
is eligible; existing publishers and tenant/source boundaries are retained. The
application's future version changes then flow automatically. Multiple hosts and
organization sources do not share version ownership. The existing opt-in NetBox
software export includes manifest provenance inside the JSON inventory; it does
not turn an application into a separate NetBox host or grant new write access.

Deployment requires migration `0066_application_manifest_observations`, server
restart and rebuilding/publishing the client from a clean reviewed checkout.
See [Ubuntu operations](../operations/ubuntu24.md). Updating only the server does
not change the binary already running on monitored hosts.
