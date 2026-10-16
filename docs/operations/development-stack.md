# Bundled and external NetBox development environments

This is a local development lab, not a production deployment. Host ports bind to loopback. No scans, real notifications or operational data publication occur. Synthetic sample inventory uses documentation address ranges. Default startup contacts only the local NetBox API after pulling/building images.

## Requirements and startup

Docker Engine/Desktop, Compose v2.24+, Python 3.10+ for the standard-library helper, about 6 GB Docker memory and 10 GB free disk are recommended. Official images advertise AMD64 and ARM64 support; the actual runtime validation was on AMD64. No local Python dependencies or uv are needed for the Docker starter. The Bearings image uses Python 3.12 and frozen `uv.lock` dependencies.

```sh
python3 scripts/dev.py up
python3 scripts/dev.py credentials
```

First startup applies NetBox's migrations and can take several minutes. The default readiness timeout is 600 seconds; use `up --timeout 900` on a slow machine. If a startup check fails, inspect `python3 scripts/dev.py status` and `python3 scripts/dev.py logs`, correct the cause, then retry `up`. Existing data is retained.

Services: Bearings web, a durable-write worker, its PostgreSQL database, official NetBox v4.7.3 / netbox-docker 5.1.1, a NetBox worker, a separate PostgreSQL database, Valkey 9.1 (separate logical DBs for queues/cache), and an Nginx 1.28 HTTPS gateway. Short-lived initializers generate secrets/certificates, provision the isolated NetBox, and migrate/prepare Bearings before serving requests. Valkey and databases expose no host ports in this stack. The old minimal `compose.yaml` remains available independently.

`compose.dev.yaml` defines Bearings and its storage; `compose.netbox.yaml` adds the bundled backend. The helper selects files and isolated project names. The default bundled project is `bearings-dev`. Export `BEARINGS_DEV_PROJECT` to use another project namespace. Ports default to Bearings 8000 and NetBox HTTPS 8443; set `BEARINGS_PORT` / `NETBOX_PORT` in your shell or a gitignored `.env` file before startup to change them. The Compose runtime can also load additional operator-owned credential variables from `.env`; bare host Django still does not auto-load that file.

## Docker prerequisite errors on macOS

`FileNotFoundError: ... 'docker'` means the Docker CLI is not installed or is missing from your terminal's PATH. With Homebrew, install Docker Desktop using `brew install --cask docker`, then launch it with `open -a Docker`. Complete first-run setup and wait until Docker Engine is running. If already installed, open Docker Desktop and check its CLI installation/PATH settings; reopen the terminal after changing them.

Verify `docker --version`, `docker compose version` and `docker info` before retrying `python3 scripts/dev.py up`. Run `python3 scripts/dev.py credentials` only after startup succeeds. Installing only the Docker CLI does not supply the engine needed to run the lab. The helper checks these prerequisites before changing active lab state; `configure` can still be used without Docker.

## Accounts and sample data

`credentials` intentionally displays only the generated initial local login password, never API tokens. New users share it: Bearings `platform-admin` (platform superuser), `company-admin` (organization administrator), `circl-analyst` (CIRCL role), plus bundled NetBox `netbox-admin`. Existing passwords, disabled users, memberships and connection capability changes are preserved. To change a Bearings password, use `python3 scripts/dev.py manage changepassword company-admin` (or the relevant account). A changed password is not reflected in the original generated-password file.

Two synthetic NetBox tenants exercise different capabilities, each with a separate non-superuser service account, scoped object permissions and v2 token. The upstream read-only token also disables writes. Write defaults and a filterable `bearings_id` custom field are provisioned for the writable example. NetBox has a device, VM, prefix and IP per tenant. Bearings verifies the sample identities through the real API before projecting just those known seed objects and adding synthetic software relationships. The Example Labs fixture workspace remains separately labeled.

The initializer verifies only its explicit seeds. The running worker now imports general devices, VMs, IP addresses and prefixes every 15 minutes by default; **Refresh inventory** queues an earlier import. Portal submissions to the writable connection do create real local NetBox objects and are confirmed by the worker. Read-only connections block portal and queued external writes. Local software entry still follows membership policy.

On restart, seeded objects use stable identities, keys and passwords are reused, and existing source identities/policies are not repointed. Bootstrap refuses conflicting identities rather than overwriting local work. It does not re-enable disabled connections or raise a read-only connection back to read/write.

## TLS and secrets

Secrets are generated in private Docker volumes; API keys are never embedded in Compose files, logged, stored in the Bearings database, or supplied as command-line values. The NetBox process reads its database password, Django secret and token pepper through the official Docker secret-file mechanism. Bearings receives only its scoped API keys, local Django secret and a public trust bundle. Its containers do not receive the NetBox database password, pepper, server private key or CA private key.

A local CA signs certificates for the development gateway. Bearings uses a CA bundle containing normal public roots plus that local CA. Certificates and hostnames are verified. `allow_private` explicitly approves the Docker-private destination; it does not disable TLS.

```sh
python3 scripts/dev.py trust
```

This exports the public CA to `.local/dev-stack/netbox-ca.crt`. To open NetBox at `https://localhost:8443`, import/trust this certificate in your local browser/OS after confirming it belongs to your own lab. It is not installed system-wide automatically. Alternatively, verify a request with `curl --cacert .local/dev-stack/netbox-ca.crt https://localhost:8443/login/`. Do not bypass verification. Private keys remain in Docker volumes. The CA lasts ten years; leaf certificates last 397 days and are renewed near expiry with a gateway reload on startup.

NetBox and Bearings use different session/CSRF cookie names, and NetBox cookies are HTTPS-only, so local browser sessions do not overwrite each other. NetBox telemetry/release checks are disabled; its SMTP destination is an unused loopback port, so mail delivery is unavailable rather than reaching any real company. Bearings retains file-based development delivery.

## Existing/external NetBox

Configure an approved instance, providing only a URL/scope/capability in arguments. The token is read without echo:

```sh
python3 scripts/dev.py configure --url https://netbox.example.org --tenant-id 42
python3 scripts/dev.py up --external
```

Use `--dedicated` instead of `--tenant-id` only when the organization is explicitly authorized to read the entire instance. Default capability is read-only. Use `--auth-scheme Token` for a verified legacy contract; current tokens use `Bearer`. Use `--allow-private` for an approved private/VPN destination and `--ca-file /path/to/approved-ca.crt` for a private CA. HTTPS endpoints may specify non-default ports; certificates are still verified. For noninteractive setup, `--token-file /path/to/secure-token-file` avoids echo, command history and token values in arguments.

Explicit `--access-mode read_write` permits subsequent authorized portal submissions; device writes need `--site-id`, `--role-id` and `--device-type-id`, and VM writes use the site default. Provision the filterable `bearings_id` custom field on the external target before enabling write workflows. External initialization performs GETs only; it never provisions accounts, taxonomy, inventory or keys on that server. The running worker can process explicitly submitted pending writes for approved read/write connections, including after a restart. External workspace CIRCL analyst visibility defaults denied and remains operator-owned.

Configuration and token files are stored under gitignored `.local/dev-stack/external/` with private permissions. A public CA file can be copied there if supplied. Each endpoint/scope/access choice derives a separate credential reference and development project/database; a token for a new endpoint cannot silently replace the key used by an old instance. Configure a different target, then run `up --external` again. Existing lab volumes remain recoverable.

External mode starts only Bearings, its worker/database and local initializers. It starts no NetBox backend or cache services. The target must be reachable from Docker, not just from the host shell: configure local/VPN DNS, approved outbound rules, or an appropriate Docker network for your environment. For a service on the host, `host.docker.internal` behavior depends on Docker Desktop/Linux routing, listener address and certificate SANs; use a genuinely reachable approved HTTPS endpoint. Never compensate with insecure TLS settings.

An unavailable or unauthorized external server is recorded in query health while the local portal remains usable. Successful container startup does not prove the remote connection works: run `query` and inspect workspace read health. The worker imports external inventory using GETs only with the configured tenant/dedicated scope. Periodic import is enabled by default; operators can pause it or change the interval in InventorySource administration.

## Daily commands and data preservation

```sh
python3 scripts/dev.py status
python3 scripts/dev.py query
python3 scripts/dev.py manage sync_netbox --all
python3 scripts/dev.py manage check
python3 scripts/dev.py manage changepassword company-admin
python3 scripts/dev.py down
```

The `manage` wrapper loads the runtime secret references and CA bundle before running Django commands. A plain `docker exec ... manage.py` does not load those files. The worker processes due writes every five seconds. Reminders and verification messages remain local files; no production transport is enabled.

`up` selects bundled mode; `up --external` selects the configured external environment. Switching stops/removes the previous lab's containers/networks, retains all named volumes, and starts the chosen environment. Switching back restores its data. `down` also preserves all volumes. Other checkouts, bare-host SQLite data and the old minimal Compose stack are untouched. There is no automatic destructive reset. Treat manual volume deletion as data loss and back up before doing it. `.local/dev-stack/active.json` remembers which helper-managed project `status`, `logs`, `credentials` and `down` address.

Docker volumes retain credentials and database state. Copying or restoring only a database without its matching secret/pepper volumes can invalidate tokens; investigate mismatches rather than silently replacing credentials. Applications and workers must restart after snapshot restoration; running processes are not portable snapshot state.

## Verification and CI

```sh
python3 scripts/dev.py smoke
```

The smoke command refuses external mode or unexpected destinations. Against the bundled synthetic lab it validates the real TLS connection, four scoped query types, upstream and portal read-only denial, both logins, device/VM creation through the background worker and recovery from a simulated lost acknowledgement without duplicates. It retains two synthetic portal-created smoke assets and also creates/updates/deletes one synthetic NetBox import probe owned by that invocation. Its local missing projection remains retained; existing user data is not deleted. Run it with the original generated demo credentials; if you changed them, use your own functional checks rather than resetting accounts implicitly.

The Development stack GitHub Actions workflow runs the same startup/smoke commands, stops without deleting volumes, restarts, and re-queries the backend. Unit tests separately cover external configuration privacy, bootstrap guards, identity conflicts and preservation of operator state. Failures collect service logs, not credentials or volume contents. See docs/validation.md for actual session results.

In the proxy-only Codex cloud sandbox, build first with `uv run python scripts/cloud_image_build.py`, then use `python3 scripts/dev.py up --no-build`. That helper supplies the existing approved build proxy and temporary CA without embedding them in the image. NetBox's internal Docker HTTPS connection does not need an external proxy. Corporate/VPN external destinations need their own explicitly approved runtime networking/trust configuration.

Docker storage drivers that copy entire image trees (`vfs`, used in this cloud) can consume substantially more space and inodes than normal Docker Desktop/overlay storage. Check both `docker system df` and host inode limits if startup reports no space; preserve database and secret volumes when reclaiming disposable build cache. The full-stack CI uses a standard Docker runner.

Import details, source field ownership and missing-object review are described in [synchronization](synchronization.md). The worker processes writes first, then due imports; an upstream import failure is recorded without stopping later sources or subsequent worker iterations.

Bundled source links use a separate HTTPS browser URL (`localhost` with the configured NetBox port), while API traffic retains the internal verified Docker hostname. An existing empty browser URL is initialized on upgrade; operator-customized URLs are preserved. If changing the gateway port after first startup, update the instance browser URL in platform administration as well.

## Public intelligence and risk scenarios

The initializer registers a public MOSP source without external HTTP. The worker periodically refreshes its CC0 MONARC catalog after inventory processing; outages retain existing evidence and do not prevent portal startup. Run `python3 scripts/dev.py manage sync_mosp --all` to request a refresh immediately, then follow the [NetBox → Vulnerability-Lookup → MOSP workflow](../integrations/mosp.md). CVEs and justified risk links are selected explicitly; bootstrap does not infer affectedness or create risk assessments for imported inventory.
