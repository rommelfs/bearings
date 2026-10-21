# Optional bundled RT 5 reference lab

Start Bearings, NetBox, FlowIntel, RT and their shared Keycloak with one command:

```sh
git pull
python3 scripts/dev.py up --sso --flowintel --rt
python3 scripts/dev.py trust
python3 scripts/dev.py credentials
python3 scripts/dev.py sso-smoke
python3 scripts/dev.py smoke
```

Import the exported **public** lab CA into the browser/OS. If it is already trusted, RT uses that same root. No CA private key is exported and all TLS verification stays enabled. Allow roughly 10 GB of Docker memory and 15 GB of disk for the combined lab; first RT image build installs its dependencies and can take several minutes. The Debian packages support native AMD64 and ARM64. This is synthetic local development, not a production RT deployment.

| Application | Default browser URL | Demo sign-in |
|---|---|---|
| Bearings | http://localhost:8000 | SSO: `company-admin` / `circl-analyst` |
| NetBox | https://localhost:8443 | OpenID Connect, same provider session |
| FlowIntel | https://localhost:9443 | Sign in with SSO, `circl-analyst` only |
| RT | https://localhost:9445 | Automatic OIDC, same provider session |
| RT local recovery | https://localhost:9446 | Local `root` account and generated demo password |

`credentials` displays the private generated local-development password. Existing account passwords are never reset. Recovery has a separate FastCGI process pool and RT cookie from the SSO entrance; a recovery login cannot authenticate the main SSO entrance. Both browser entrances bind to host loopback. Do not publish this recovery entrance or use the local lab's password/MFA policy for production.

## What is configured automatically

The pinned reference is **Debian RT 5.0.7+dfsg-4+deb13u3** (including Debian security fixes), Apache with FastCGI and mod_auth_openidc, and a separate PostgreSQL 17 database. RT keeps its own GPL notices under `/usr/share/doc/request-tracker5/copyright`; the distribution's source package is available from [Debian](https://tracker.debian.org/pkg/request-tracker5). Add `--rtir` to install native RTIR 5.0.10, retained CIRCL-only Incidents and linked Investigations; see the [RTIR lab](rtir-lab.md). Plain `--rt` leaves the extension inactive until explicitly installed.

The starter creates a distinct confidential Keycloak client in the retained lab realm, an exact HTTPS callback, PKCE and fixed certificate-verified internal endpoints. Explicit immutable subjects bind to the existing `company-admin` and `circl-analyst` RT accounts. Unknown subjects, email/group matches and disabled local RT accounts do not gain access. RT application accounts resolve to their verified local numeric ID, avoiding RT's ambiguous handling of all-numeric username strings. No claim grants an RT role.

Two private synthetic queues are separate:

- **Bearings-company**: the company human and its own narrowly scoped API bridge. Bearings binds this connection to the bundled read/write NetBox organization.
- **Bearings-circl**: the CIRCL human and a separate scoped API bridge. Bearings exposes this connection only to authorized CIRCL reviewers for currently visible organizations.

Humans can review/update their own queue. Bridges can create/read tickets in their own queue, have no local password and use separate server-side token files. They do not inherit root/global rights. `platform-admin` is not an RT SSO identity; RT's `root` is local recovery only. Probe tickets and example contacts contain synthetic data only.

Both Bearings RT connections are initially enabled and attested for this isolated fixture. Existing disabled connections, queue confirmation policies, user/account disabled state, ACL edits, passwords, tokens and tickets are preserved on subsequent startup. Renamed/deleted reserved identities or a conflicting retained source/client fail startup without recreating accounts, granting old permissions again or rotating secrets. Lost private token files require recovery, not blind bootstrap rotation. Deliberate endpoint/port changes require an isolated project instead of repointing retained identities.

The RT service and database run on an **internal Docker network with no Internet route**. The existing HTTPS edge gateway forwards to RT using verified HTTPS; the one-off IdP provisioner is separate and applications do not receive its administrator credential. RT's documented `mbox` mail mode retains messages under the RT data volume; no SMTP destination or mail-gateway exception is enabled. Keep these defaults for the synthetic lab. No production messages, scans or remediation are triggered by login or startup.

## Exercise the Bearings hand-off

Open **Asset issues** in Bearings and select an existing synthetic issue. If needed, populate the local lifecycle exercise first:

```sh
python3 scripts/dev.py manage seed_asset_issues --bundled
```

As company administrator, **Prepare RT ticket** targets `bundled-rt-company`. As an authorized CIRCL analyst, the CIRCL destination `bundled-rt-circl` is also available for operator-visible issues. Review the exact asset/IP/DNS/rack, issue/evidence/risk content and destination, then approve the draft. The worker creates the ticket once, verifies its queue/subject/effective identity and exposes a clickable RT link. An uncertain POST is reconciled through bounded GET/search requests rather than retried. Remote completion does not resolve a Bearings issue or assert remediation. Status, owner and due date remain separate feedback; outages retain the last-known state.

`smoke` exercises real create/read, company/CIRCL token isolation, foreign-ticket denial, stable mapping and a simulated lost acknowledgment recovered through GET-only search. It also checks actual RT human queue ACLs, local-only mail configuration and absence of an Internet route. `sso-smoke` exercises real Keycloak authorization-code sign-in, company/CIRCL permitted and forbidden tickets, unassigned identity denial and local emergency login without sharing its session into SSO. Neither command writes to an external installation. The source and queue guards refuse modified/non-lab targets.

## Start, stop and retain data

The starter remembers all flags. Later starts need only:

```sh
python3 scripts/dev.py up
```

For RT and NetBox without FlowIntel use `up --rt --no-flowintel --sso`. For the local-password RT path use `up --rt --no-sso`; the normal RT entrance then accepts the seeded RT human logins and local root account. `up --no-rt` stops the optional RT service and retains its volumes and Bearings mappings. Re-enable with `up --rt`. While RT is stopped the retained connector may report unavailable transport; that is not deletion or remediation. `down` stops the lab and retains data. Do not delete volumes as an upgrade or repair step.

RT is restarted after a successful `up` so new generated subject-map/active-account checks reach every FastCGI process, even when only bind-mounted adapter files changed. Database data, keys and ACLs are preserved. Apache's OIDC session cache is process-local; a retained Keycloak session normally signs in again without a password. RT user/queue policies remain independent of Bearings membership policies. Global logout, IdP backchannel revocation, enforced MFA for local passwords and production operational acceptance remain separate work.

The first install initializes an empty database once. Existing schemas are retained; this pinned increment does not perform automatic major/version migrations. If initialization fails, inspect `python3 scripts/dev.py logs` and private configuration/DB health without posting credentials or raw provider responses. A deliberately rotated IdP operator credential must be updated in its private provisioner input rather than resetting the realm. Another service occupying the chosen host ports needs a deliberate isolated configuration, not disabled TLS checks.

For a separately operated RT/RTIR use the [external deployment bundle](rt-sso.md) and [RT connector guide](../integrations/rt-rtir.md). The optional RTIR lab covers native Incident/Investigation lifecycles and relationships; customer-specific overlays, queues and mail scrips still need acceptance. See [validation](../validation.md) for exact live outcomes.
