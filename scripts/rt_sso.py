"""Generate an explicit RT 5.x Apache/OIDC deployment bundle, using only stdlib.

No remote changes, user creation, queue changes or secret values on stdout.
"""

import argparse
import json
from pathlib import Path
import re
import secrets
from urllib.parse import urlsplit

from scripts.dev import private_file


def https_url(value, *, origin=False):
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError:
        raise ValueError("Invalid HTTPS port") from None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or port == 0
        or re.search(r'[\s"\\<>${}]', value)
        or (origin and parsed.path not in {"", "/"})
    ):
        raise ValueError("Use a credential-free HTTPS URL; RT must have its own origin at /")
    return value.rstrip("/")


def generate(directory, issuer, rt_url, mapping, client_secret, *, client_id="rt", ca_path=None):
    issuer, rt_url = https_url(issuer), https_url(rt_url, origin=True)
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", client_id):
        raise ValueError("Invalid client ID")
    if not re.fullmatch(r"[A-Za-z0-9_.~+/-]{16,256}={0,2}", client_secret):
        raise ValueError("Use a single-line URL-safe client secret of at least 16 characters")
    if not isinstance(mapping, dict) or not mapping or len(mapping) > 10000:
        raise ValueError("Provide an explicit JSON subject-to-existing-RT-username object")
    seen = set()
    for subject, username in mapping.items():
        if (
            not isinstance(subject, str)
            or not 1 <= len(subject) <= 255
            or any(ord(c) < 32 or ord(c) > 126 for c in subject)
            or not isinstance(username, str)
            or not re.fullmatch(r"[A-Za-z0-9_.@+-]{1,128}", username)
            or username.casefold() in seen
        ):
            raise ValueError("Invalid or duplicate explicit identity mapping")
        seen.add(username.casefold())
    if ca_path and not re.fullmatch(r"/[A-Za-z0-9_./-]+", ca_path):
        raise ValueError("CA bundle must be an absolute server file path")
    directory = Path(directory)
    if directory.is_symlink():
        raise ValueError("Refusing a symlink output directory")
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o700)
    crypto_path = directory / "oidc-crypto-passphrase"
    if crypto_path.is_symlink():
        raise ValueError("Refusing a symlink output")
    crypto = crypto_path.read_text().strip() if crypto_path.exists() else secrets.token_urlsafe(48)
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", crypto):
        raise ValueError("Invalid retained OIDC cookie encryption secret")
    callback = rt_url + "/NoAuth/bearings-oidc"
    apache = f'''# Include INSIDE the existing RT HTTPS VirtualHost executing RT FastCGI/mod_perl.
# Requires mod_auth_openidc >= 2.4.16, mod_headers and a server-side session cache.
# No HTTP reverse-proxy header-to-REMOTE_USER translation is installed.
OIDCProviderMetadataURL "{issuer}/.well-known/openid-configuration"
OIDCClientID "{client_id}"
OIDCClientSecret "{client_secret}"
OIDCCryptoPassphrase "{crypto}"
OIDCRedirectURI "{callback}"
OIDCResponseType code
OIDCPKCEMethod S256
OIDCScope "openid"
OIDCRemoteUserClaim sub
OIDCSSLValidateServer On
OIDCValidateIssuer On
OIDCPassClaimsAs environment
OIDCSessionType server-cache
OIDCSessionMaxDuration 1800
OIDCSessionInactivityTimeout 1800
OIDCCookieHTTPOnly On
OIDCCookieSameSite Lax
{('OIDCCABundlePath "' + ca_path + '"') if ca_path else "# Public CA trust uses the server system CA bundle."}
# Discard spoofed identity headers. REMOTE_USER comes from the Apache auth module.
RequestHeader unset Remote-User early
RequestHeader unset X-Remote-User early
RequestHeader unset X-Forwarded-User early
RequestHeader unset OIDC_CLAIM_sub early
SetEnvIf Authorization "(.*)" HTTP_AUTHORIZATION=$1
<Location "/">
    AuthType openid-connect
    Require valid-user
</Location>
# Leave API authentication to RT, including the Bearings scoped REST2 token.
# This exemption does not grant anonymous RT API permissions.
<LocationMatch "^/REST/2\\.0(?:/|$)">
    AuthType None
    Require all granted
</LocationMatch>
# Do not log callback query strings, Authorization headers or cookies.
LogFormat "%h %m %U %>s" bearings_rt_safe
CustomLog /var/log/apache2/rt-sso-access.log bearings_rt_safe
LogLevel warn auth_openidc:warn
'''

    def perl(value):
        return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"

    entries = "\n".join(
        f"    {perl(subject)} => {perl(username)}," for subject, username in sorted(mapping.items())
    )
    overlay = (
        """# Install as local/lib/RT/Interface/Web_Local.pm only if no overlay exists.
# If it exists, merge this function through your RT operator. Never overwrite it.
package RT::Interface::Web;
use strict;
use warnings;
no warnings 'redefine';
my %bearings_approved_subjects = (
"""
        + entries
        + """
);
sub WebCanonicalizeInfo {
    my $subject = RequestENV('REMOTE_USER');
    return undef unless defined $subject;
    # Exact, case-sensitive immutable OIDC subject. No email/name/group association.
    return $bearings_approved_subjects{$subject};
}
1;
"""
    )
    site = """# Merge into RT_SiteConfig.pm; keep existing database/queue/mail settings.
Set($WebRemoteUserAuth, 1);
Set($WebRemoteUserContinuous, 1);
Set($WebRemoteUserAutocreate, 0);
Set($WebRemoteUserGecos, 0);
Set($WebFallbackToRTLogin, 0);
Set(%WebRemoteUserAdditionalMapping, ());
Set($AutoLogoff, 30);
1;
"""
    client = {
        "clientId": client_id,
        "protocol": "openid-connect",
        "enabled": True,
        "publicClient": False,
        "secret": client_secret,
        "standardFlowEnabled": True,
        "implicitFlowEnabled": False,
        "directAccessGrantsEnabled": False,
        "serviceAccountsEnabled": False,
        "fullScopeAllowed": False,
        "redirectUris": [callback],
        "defaultClientScopes": [],
        "attributes": {"pkce.code.challenge.method": "S256"},
    }
    manifest = {"issuer": issuer, "rt_url": rt_url, "client_id": client_id, "mapping": mapping}
    files = {
        "apache-oidc.conf": apache,
        "Web_Local.pm": overlay,
        "RT_SiteConfig_SSO.pm": site,
        "keycloak-client.json": json.dumps(client, indent=2) + "\n",
        "manifest.json": json.dumps(manifest, indent=2) + "\n",
        "oidc-crypto-passphrase": crypto + "\n",
    }
    # Check every output before writing anything; retained policy or credentials are never silently reset.
    for name, value in files.items():
        path = directory / name
        if path.is_symlink() or (path.exists() and path.read_text() != value):
            raise ValueError(
                "Retained RT SSO bundle differs; choose a new output directory and review changes"
            )
    for name, value in files.items():
        private_file(directory / name, value)
    return callback


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issuer", required=True)
    parser.add_argument("--rt-url", required=True, help="Dedicated RT HTTPS origin, without a subpath")
    identities = parser.add_mutually_exclusive_group(required=True)
    identities.add_argument("--subject-map", help="Private JSON: immutable subject -> existing RT username")
    identities.add_argument("--subject", help="One verified immutable IdP subject")
    parser.add_argument("--rt-user", help="Existing RT username for --subject")
    parser.add_argument(
        "--client-secret-file",
        help="Optional existing client secret; otherwise generated and retained privately",
    )
    parser.add_argument("--client-id", default="rt")
    parser.add_argument("--ca-path", help="Optional public CA bundle path on the Apache server")
    parser.add_argument("--output", default=".local/dev-stack/rt-sso")
    args = parser.parse_args(argv)
    try:
        if args.subject:
            if not args.rt_user:
                raise ValueError("An existing RT username is required")
            mapping = {args.subject: args.rt_user}
        else:
            if args.rt_user:
                raise ValueError("Use either a mapping file or a subject/username pair")
            mapping = json.loads(Path(args.subject_map).read_text())
        saved = Path(args.output) / "keycloak-client.json"
        if args.client_secret_file:
            secret = Path(args.client_secret_file).read_text().strip()
        elif saved.is_symlink():
            raise ValueError("Refusing a symlink client configuration")
        elif saved.exists():
            secret = json.loads(saved.read_text())["secret"]
        else:
            secret = secrets.token_urlsafe(48)
        callback = generate(
            args.output,
            args.issuer,
            args.rt_url,
            mapping,
            secret,
            client_id=args.client_id,
            ca_path=args.ca_path,
        )
    except (ValueError, OSError, KeyError, TypeError):
        raise SystemExit(
            "RT SSO bundle not written: check HTTPS URLs, private input files and retained output policy. No secrets were logged."
        ) from None
    print("Private RT SSO bundle prepared in " + args.output)
    print("Register the generated client with the same IdP; exact callback: " + callback)
    print(
        "Install through the RT Apache operator and follow docs/operations/rt-sso.md. No remote service or RT account was changed."
    )


if __name__ == "__main__":
    main()
