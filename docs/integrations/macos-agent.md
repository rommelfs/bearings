# Bearings inventory client for macOS

Bearings.app is a self-contained macOS inventory client for Intel and Apple
Silicon Macs running macOS 13 or later. It uses the configured server's HTTPS
origin and the macOS trust store. Reports use an independent Ed25519 device key,
signed observations, sequence numbers, acknowledgments and a private on-disk
queue.

## Publish without Apple signing

On Ubuntu, the regular client build publishes the Apple Silicon and Intel
ZIPs without requiring a Mac signing station. A previously published notarized
release takes precedence. The unsigned build includes the Bearings mark as
128- and 256-pixel ICNS images and
uses Go's platform-required ad-hoc executable signing on Apple Silicon. An
Ed25519 Bearings release manifest authenticates automatic updates on HTTPS.

```sh
cd /opt/bearings
python3 deploy/ubuntu24/ecosystem.py prepare-clients
```

Use an unsigned release only on Macs whose software policy permits it.
Finder can block unsigned browser downloads. After verifying the server's
SHA-256 checksum and extracting the ZIP, start the client from Terminal in
the extracted directory. A macOS policy that blocks the unsigned executable
requires an approved release from your software distribution process. The
unsigned client accepts a valid local ad-hoc signature and keeps its bundle
seal during installation. If an installation has a local seal, authenticated
client updates are also sealed with the built-in macOS signing tool. macOS
still decides whether to allow the new executable to launch.

```sh
./Bearings.app/Contents/MacOS/bearings-macos
```

The unsigned and Apple-signed builds have distinct update manifests. Migrating
between them requires installing the newly approved bundle. The device
registration is stored separately.

## Publish with Apple signing

The Ubuntu publisher asks the signing Mac to build the currently deployed Git
revision. The Mac builds both architectures, adds the Bearings icon, signs and
notarizes the apps, staples the tickets, and returns the release through SSH.
Ubuntu checks the signed manifest, HTTPS origin, sequence and ZIP hashes before
switching the downloads. Failed builds or transfers retain the last release.
The timer checks every 15 minutes and skips revisions that were published
successfully. The usual server upgrade requires no macOS-specific command.

### Configure the signing Mac once

Use a dedicated Mac account and clean checkout of the Bearings repository.
Install Go, uv, and the Xcode command-line tools. Import the organization's
**Developer ID Application** identity into a release keychain and configure an
Apple `notarytool` keychain profile. Make the signing identity and profile
accessible without interactive prompts to the dedicated SSH account. Test
keychain access in that account's noninteractive SSH session. Apple
credentials remain on the Mac.

Provide the same protected Bearings Ed25519 release seed on Ubuntu and the
Mac. Reuse the existing `macos-release.key` where one already exists. For a
first release, provision the same base64-encoded 32-byte key in both private
locations. The previous manifest and the resulting artifacts travel
automatically. Release keys belong outside the repository and download paths.

Save a private `signer.json` owned by the Mac account. Example:

```json
{
  "origin": "https://bearings.example.org",
  "checkout": "/Users/bearings/bearings-signing",
  "approved_ref": "refs/heads/main",
  "lock": "/Users/bearings/private/signing.lock",
  "uv": "/Users/bearings/.local/bin/uv",
  "go": "/opt/homebrew/bin/go",
  "release_key": "/Users/bearings/private/macos-release.key",
  "apple_identity": "Developer ID Application: Example Organization (TEAMID1234)",
  "apple_team": "TEAMID1234",
  "notary_profile": "bearings-notary"
}
```

Set `approved_ref` to the protected branch or reviewed tag that contains the
deployed revision. The signing account runs release code from commits
reachable from that ref in the Bearings GitHub repository. Protect the ref
accordingly. Install a reviewed copy of `scripts/macos_signing.py` **outside**
the signing checkout so the SSH entry point stays fixed. Authorize the
publisher's dedicated SSH public key with a forced command in the signing
account's `authorized_keys`:

```text
restrict,command="/absolute/path/python3 /Users/bearings/private/macos_signing.py serve --config /Users/bearings/private/signer.json" ssh-ed25519 PUBLIC_KEY
```

### Configure Ubuntu once

Create these root-owned files under `/etc/bearings/ecosystem` with mode
`0600`:

| File | Contents |
| --- | --- |
| `macos-signer` | SSH destination in `user@host` form |
| `macos-signer.key` | Dedicated noninteractive SSH private key |
| `macos-signer.known_hosts` | The Mac SSH host key verified through a trusted channel |
| `macos-release.key` | Existing or newly provisioned Bearings macOS release seed |

From the updated Ubuntu checkout:

```sh
cd /opt/bearings
python3 deploy/ubuntu24/ecosystem.py enable-macos-release
systemctl list-timers bearings-macos-release.timer
journalctl -u bearings-macos-release.service -n 60 --no-pager
```

The timer detects the next deployed revision and publishes it when Apple
accepts the build. The standard `prepare-clients` command also installs or
refreshes the timer when the signer is configured. An operator can use
`systemctl start bearings-macos-release.service` to run the same automated
check immediately. A manual import of a signed release remains available
through `prepare-clients --macos-release DIRECTORY` for recovery.

## Download and install

1. Open **Inventory clients → macOS** on your Bearings server.
2. Check **Apple menu → About This Mac** and download the Apple Silicon or Intel
   ZIP for that Mac. Verify its checksum according to your deployment policy.
3. Extract the ZIP and open **Bearings.app** as the user who will send reports.
4. Choose **Register and enable reports** and paste your organization's rollout
   key. Administrators create keys under **Inventory clients → Rollout keys**.
   The existing rollout policy controls the tenant, inventory source and quota.
   The Mac generates its own key and registers itself.
5. Choose **Check report status** and look for **applied**. **Pending** means the
   server has received the report and is still processing it.

The Apple-signed release contains a Developer ID-signed app with a stapled
notarization ticket. The download page identifies unsigned releases. If you previously downloaded the unsigned build, download the
replacement and open it. Run **Register and enable reports** to repair an
existing installation using its retained device state. For a private HTTPS
CA, distribute the trust certificate through macOS before installation.

## Rollout, reporting and updates

For managed rollout, stream the rollout key on stdin from the deployment secret
manager in the reporting user's active graphical session. The same install
command can retry an interrupted registration or repair a failed launch-agent
setup.

```sh
./Bearings.app/Contents/MacOS/bearings-macos install
```

The app installs to `~/Applications/Bearings.app`. Its launch agent runs at
sign-in and every 15 minutes during the user's graphical session, including
after opening and closing the app. A first run and inventory changes send full
observations. Once the server accepts a complete baseline, unchanged runs send
compact signed check-ins. Inaccessible inventory leaves existing observations
in place and reduces recorded coverage. Bearings identifies unreadable
installed applications, system applications, installer receipts or Homebrew
sources. The local summary lists the first 50 affected paths and errors
without transmitting them or accessing credentials:

```sh
"$HOME/Applications/Bearings.app/Contents/MacOS/bearings-macos" coverage
```

Earlier client reports can only identify an unspecified macOS software gap.
The first full capture establishes the complete-inventory baseline.

The client observes the running macOS version, build and Darwin kernel, app
bundles under `/Applications` and `/System/Applications`, installer receipts and
formulae in standard Homebrew Cellars. Installer receipts represent recorded
package installations. User application directories, custom Cellars, the Apple
Software Update catalogue and third-party application patch availability are
outside this collection scope. Generic macOS identities are suitable for
explicit product-watch mapping. Apple build-specific vulnerability and
remediation rules require dedicated evidence.

The client periodically checks its own updates from the configured server.
It verifies the pinned publisher signature, increasing release sequence, hash
and Apple code signature before replacing the complete app bundle.
Replacing the complete bundle preserves its icon, signature and notarization.
The next run executes the replacement, keeping the device key, counter and
queue. Use **Check for client update** to check immediately. Automatic client
updates can be turned off in the app.

## Troubleshooting and uninstall

Choose **Archive failed registration** to retain an abandoned local registration
request and retry with a valid key. Complete or already authorized registrations
cannot be overwritten by this action. Ask the administrator to review a
reservation if the client already received an enrollment grant.

In the installed app use **Send report**, **Check report status** or **Uninstall**.
The corresponding terminal commands are:

```sh
client="$HOME/Applications/Bearings.app/Contents/MacOS/bearings-macos"
"$client" report
"$client" status
"$client" update
"$client" uninstall
```

Local uninstall confirms deregistration with Bearings, removes the application,
launch agent and private state under the reporting account, and requires
connectivity to the server. If a transmission is interrupted, retry after
connectivity returns. Administrators may also request uninstall on the device
in **Client inventory observations**. The next automated run acknowledges
retirement and removes the local installation.
