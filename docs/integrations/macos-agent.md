# Bearings inventory client for macOS

Bearings.app is a self-contained macOS inventory client for Intel and Apple
Silicon Macs running macOS 13 or later. It uses the configured server's HTTPS
origin and the macOS trust store. Reports use an independent Ed25519 device key,
signed observations, sequence numbers, acknowledgments and a private on-disk
queue.

## Publish the downloads

On a native Ubuntu Bearings installation, update to a reviewed server revision,
apply any server migrations and run the following from the checkout as the server operator.

```sh
cd /opt/bearings
python3 deploy/ubuntu24/ecosystem.py prepare-clients
```

The command builds Linux, Windows and macOS downloads in one release directory
and restarts the web service. Use `--no-restart` when running it before a planned
service start. It configures the HTTPS origin from `BEARINGS_PUBLIC_URL` and
creates a separate protected `macos-release.key` on first publication. Back up
that key with the other protected deployment credentials. Later releases reuse
the key and advance the signed sequence. Publish subsequent server revisions
with the same command to distribute updated client builds.

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

The stock ZIP is built without Apple Developer ID signing or notarization. Where
Gatekeeper blocks it, use your organization's macOS software approval process.
For a private HTTPS CA, distribute the trust certificate through macOS before
installation.

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
in place and reduces recorded coverage.

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
and executable architecture before atomically replacing the installed binary.
The next run executes the replacement, keeping the device key, counter and
queue. Use **Check for client update** to check immediately. Automatic client updates can be turned off in the app.

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
