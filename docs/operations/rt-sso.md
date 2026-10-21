# RT / RTIR SSO deployment bundle

Bearings includes a standard-library configuration generator for **RT 5.x / RTIR behind Apache 2.4 with mod_auth_openidc >= 2.4.16**, executing RT through its existing FastCGI/mod_perl integration. It uses the same OIDC issuer as Bearings, NetBox and FlowIntel and a **separate confidential client**. This is an integration package for an existing RT installation, not a bundled RT server or a replacement for its database/queue/mail configuration. Nginx-only or HTTP-proxied RT deployments need an authentication-aware Apache layer at the RT execution boundary; forwarding a browser header as `REMOTE_USER` is not supported.

## Prepare one private bundle

Use the immutable subject from the approved provider, not an email address or display name. Choose an existing RT username with reviewed queue permissions:

```sh
python3 scripts/dev.py rt-sso \
  --issuer https://idp.example.org/realms/example \
  --rt-url https://rt.example.org \
  --subject VERIFIED-IMMUTABLE-SUBJECT \
  --rt-user existing-analyst
```

Docker and Python packages are not required for this generator. It creates `.local/dev-stack/rt-sso` with directory mode 0700 and files mode 0600, prints no credentials and makes **no remote changes**. A separate client secret and cookie-encryption key are generated automatically. Repeating the same command preserves both; changed identity/endpoint/credential settings are refused in the existing output directory. Generate a new directory with `--output` to review a deliberate change. Never commit, paste into issues or publish the generated bundle.

For multiple users, use `--subject-map /private/rt-subjects.json` instead of `--subject/--rt-user`. The JSON object maps exact case-sensitive subjects to existing RT usernames. Duplicate local usernames are rejected. `--client-secret-file` can supply an existing private client credential; `--client-id` selects a distinct registration for another RT deployment. `--ca-path /server/path/approved-ca.pem` adds an approved public CA bundle on the Apache host. TLS and issuer verification stay enabled. This increment requires a dedicated RT HTTPS origin at `/`, without a URL subpath.

## Install on the existing RT host

1. Register/import **`keycloak-client.json`** in the same Keycloak realm. For another conforming OIDC provider register equivalent code-flow settings: confidential client, S256 PKCE, exact callback, no implicit/password/service grant and no group-to-role mapping. Do not overwrite an existing client registration or client secret without review. The callback is exactly `https://rt.example.org/NoAuth/bearings-oidc`.
2. Enable Apache `auth_openidc`, `headers` and `setenvif`. Include **`apache-oidc.conf` inside the existing RT HTTPS VirtualHost**, alongside its working FastCGI/mod_perl handler. Restrict the private include to the Apache master process. Retain the existing certificates, RT paths and network restrictions. No HTTP backend port may bypass this authentication layer.
3. Install **`Web_Local.pm`** at the RT installation's `local/lib/RT/Interface/Web_Local.pm`, readable by the RT worker (for example owner root, RT group, mode 0640). **If a local overlay already exists, merge the generated `WebCanonicalizeInfo` function; never overwrite that file.** The mapping deliberately preserves subject case and returns no identity for an unapproved subject. This overrides RT's usual lowercase conversion; email/group claims do not link accounts.
4. Merge **`RT_SiteConfig_SSO.pm`** into the existing RT configuration. It enables continuous remote-user checks, disables account creation and ordinary password fallback on this web entry point, and leaves queue/organization/privilege settings untouched. Keep the original local administrator credentials and a separately restricted, tested recovery procedure; no public password-bypass endpoint is created.
5. Run `apachectl configtest`, the RT configuration checks appropriate to your deployment, and restart the Apache/RT workers. A worker restart is also needed after an explicit subject-map revocation. Test the deployment's normal Mason cache refresh procedure where applicable.

Only Apache's authenticated environment sets `REMOTE_USER`. Incoming identity headers are discarded. The generated `/REST/2.0/` exemption leaves authentication and queue ACLs to RT's own API middleware; the Authorization header is passed to RT for the existing scoped Bearings service token. It grants no anonymous RT access and does not share a human SSO session with the connector. Existing mail-gateway, feed and webhook exceptions need their own operator-approved access rules; none are opened by this bundle. Keep the existing primary access log from recording callback query strings too: the additional safe log cannot disable another `CustomLog` inherited from a parent configuration. Do not enable OIDC debug logging or log tokens/cookies.

## Acceptance before operational use

- Sign in through Bearings, then open RT: the provider session should avoid a second password prompt. RT's existing username and queue permissions must remain unchanged.
- Verify unknown subjects are denied even when email/group claims match an existing privileged account. Test subject case changes and spoofed `Remote-User`, `X-Remote-User`, `X-Forwarded-User` and OIDC claim headers. Direct FastCGI/backend access must be restricted to the authentication layer.
- Verify an allowed queue and a denied queue with the same SSO account. Remove a subject mapping, restart the workers and confirm the previously signed-in account loses access. Test RT account deactivation as well.
- Verify a scoped REST2 token works and an absent/invalid token is rejected; verify browser REST2 calls still use RT's own reviewed session policy. Do not create operational tickets during login tests: RT scrips can send mail.
- Test the restricted local recovery process before depending on the IdP. RT logout, Apache OIDC logout and provider logout are different sessions. Global/backchannel logout and IdP-side revocation are not guaranteed by this bundle; OIDC sessions have a maximum of 30 minutes.

The generator has executable Perl mapping, configuration-injection, private-file and retained-policy regression checks. Real Apache/mod_auth_openidc, Keycloak and a CGI identity harness additionally verify shared login and spoofed-header/foreign-identity denial at the execution boundary. A complete customer RT/RTIR installation has not been certified. Live RT version, queue ACL, overlay compatibility, cookie revocation and mail behavior require that installation's acceptance. See [SSO](sso.md), [RT connector](../integrations/rt-rtir.md) and [validation](../validation.md).
