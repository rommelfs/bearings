# Linux installation and existing roll-outs

Implemented 20 November 2026: central public artifact downloads, local privileged installer, private clipboard/stdin enrollment and operator-side one-use issuance. A customer-facing roll-out API/delegated issuer credential is **planned**, not implemented. No shared permanent fleet enrollment key is introduced.

## Existing tools: implemented contract

The operator builds the reviewed Linux client once with `python3 scripts/build_linux_client.py`. Development exposes the generated `.local/linux-client` directory; production must explicitly set `BEARINGS_LINUX_CLIENT_DIR` to an approved absolute artifact directory. Serve/mount it read-only in production. Only fixed allowlisted filenames are public; no customer inventory, credentials, arbitrary paths or unbuilt source fallback. Symlink, shared-writable, missing, oversized or manifest-mismatched artifacts are refused. Installer/manifest/unit/binaries/license/source are downloadable through `/downloads/linux/`. No database query or external fetch is required to deliver an artifact.

The downloaded installer verifies HTTPS and manifest hashes before installing a matching architecture and pinned hardened unit. Python 3.9+/systemd/root are required for the installer; native collection/enrollment runs as the dedicated account. No package manager, Go compiler, internet download script execution, untrusted shell or remote server command channel is introduced. Root actions are explicit. Source inputs are read with the invoking sudo user's permissions, preventing a supplied input path from becoming a privileged file-read proxy. Only generated public artifacts and private ephemeral grant handoff are staged; device state is retained independently. Per-file installation is atomic, not a filesystem-wide transaction. A failure retains keys/state and may require a retry/start after resolving the local error.

`identity` returns JSON `{public_key, fingerprint_sha256, enrolled}`. Install/identity preserve the existing key; do not initialize reusable VM/image templates. `enroll --code` hides terminal input; `enroll --code-stdin` accepts at most 16 KiB through stdin, for a complete one-use, expiring, key-bound grant of at most 8 KiB. Plaintext codes are not accepted as command-line values or environment variables. They are bearer credentials plus public metadata, not encrypted tickets. No file needs to cross the browser/SSH boundary; a root-controlled temporary handoff is removed even on failure. Existing `--grant-file` is retained for compatibility. A delivery retry must reuse the same protected code until acknowledgment; do not issue a fresh grant for an already pending enrollment. Store that short-lived job secret in the approved secret runner until confirmation/expiry, never in logs or image/fact caches. If it is lost, use the explicit cancellation/replacement recovery rather than resetting keys/counters. A confirmed enrolled device uses `start` to resume rather than another grant. Current source/role/revocation checks and explicit new-host/network consent are unchanged.

## Operator-controlled issuance: implemented

An approved automation runner with access to the Bearings management environment can request one code:

```sh
python manage.py issue_agent_enrollment \
  --organization company-slug \
  --actor company-rollout-account \
  --asset EXISTING-ASSET-UUID \
  --public-key PUBLIC-ED25519-KEY
```

The command prints a **secret** code to stdout for direct controlled handoff; suppress it in CI logs. Its actor must currently be an active company administrator or platform superuser. CIRCL visibility alone is insufficient. Use a dedicated company-scoped account, not a universal staff credential. A foreign asset/company, disabled actor, invalid key or invalid public origin fails without issuing a usable code. Creation is transactional and uses the existing audited thirty-minute, one-use, key-bound enrollment service. Explicit `--new-host-kind vm|server|desktop|laptop` instead of `--asset` authorizes creation only where source writes are allowed; the client must additionally use `--register-host`.

Running a management command already requires trusted server access. `--actor` is attribution/authorization inside that administrative boundary, not authentication for a public API. Customers of the SaaS are not given server shell access by this implementation. Without an approved issuer integration they obtain a code through the company UI; customer-facing delegated API access remains the next increment.

## Ansible pattern

Use `get_url` with certificate verification to obtain the installer; then use `command` with an argument list and `become: true` for install. Do not use `curl | sudo ...`. Install the lab/enterprise CA by your normal trusted platform process first. The origin must be reachable from each target: localhost is not a remote server address.

```yaml
- name: Install the reviewed Bearings client from the approved origin
  become: true
  ansible.builtin.command:
    argv: [python3, /opt/bearings-install.py, --server, "{{ bearings_origin }}"]

- name: Read the existing public device identity
  become: true
  ansible.builtin.command:
    argv: [python3, /opt/bearings-install.py, identity]
  register: bearings_identity_result
  changed_when: false

# When not enrolled, obtain one key-bound code from the approved issuer.
# For operator-owned automation, delegate the management command above to
# the controlled Bearings host. Suppress its output (no_log); do not cache it.
# SaaS customer API issuance is not implemented yet.

- name: Consume the short-lived grant without an argv/env/file secret
  become: true
  ansible.builtin.command:
    argv: [python3, /opt/bearings-install.py, enroll, --code-stdin]
    stdin: "{{ bearings_one_use_code }}"
  no_log: true
  when: not (bearings_identity_result.stdout | from_json).enrolled
```

This is an integration pattern, not a published/validated Ansible collection or a claim of a tested customer roll-out. Real installer execution, verified TLS/key proof, stdin handoff, retries, permissions and activation preservation are tested separately. Restrict job output, secret access, target/asset mappings and retries; do not reuse a code/key across machines. Review initial package-report volume before fleet-wide activation; existing 40,000-company read benchmarks are not agent-ingest evidence.

## Customer API proposal: not implemented

Add a revocable expiring issuer credential per company and approved roll-out identity. Its only operation should request an enrollment bound to one freshly generated public key and an explicit existing asset or approved new-host policy. It must not read inventory/intelligence, grant human/native-app access, change source/visibility/roles, approve network authority or install commands. Enforce current company approval/role policy, per-issuer/company quotas, narrowly allowed host kinds, audit/correlation IDs, idempotent job retries and fast revocation. Return a short-lived one-use code only to that authorized job. Device keys are generated on targets and never leave them. Establish the secret-manager/identity-provider binding and customer usability before enabling that endpoint. This should become a small supported Ansible role after actual delegated API acceptance, rather than a shared fleet bootstrap password.
