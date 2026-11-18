"""Read-only directory of local lab login accounts and actually published URLs."""

import json
import subprocess
from urllib.parse import urlsplit


def published_origin(base, run, service, port, scheme="https"):
    try:
        result = run(base + ["port", service, str(port)], capture_output=True, text=True)
        binding = urlsplit("//" + result.stdout.strip().splitlines()[0])
        number = binding.port
        if binding.hostname not in {"127.0.0.1", "localhost", "::1", "0.0.0.0", "::"} or not number:
            return None
        return f"{scheme}://localhost:{number}"
    except (subprocess.CalledProcessError, IndexError, ValueError):
        return None


def directory(state, base, run, external_config):
    print("LOCAL DEVELOPMENT LOGIN DIRECTORY")
    print(
        "Generated initial passwords are shown per service. Changed passwords, disabled accounts and grants are preserved."
    )
    print(
        "Self-registered users use their own chosen passwords; API/service accounts are not interactive demo logins."
    )

    def origin(service, port, scheme="https"):
        return published_origin(base, run, service, port, scheme)

    def url(host, path="/"):
        return host + path if host else "[not published; start the selected lab profile]"

    def secret(label, service, path):
        print(label, flush=True)
        try:
            result = run(base + ["exec", "-T", service, "cat", path], capture_output=True, text=True)
        except subprocess.CalledProcessError:
            print("    unavailable; the selected service or its retained password file is not accessible")
        else:
            print(result.stdout, end="" if result.stdout.endswith("\n") else "\n", flush=True)

    http = origin("web", 8000, "http")
    bearings = origin("bearings-tls", 443) if state.get("sso") else http
    print("\nBEARINGS")
    print("  Local login: " + url(bearings, "/accounts/login/"))
    print("  platform-admin — LOCAL Username/Password form, Sign in; not a Keycloak identity")
    print("  company-admin, circl-analyst — local Username/Password form")
    if state.get("sso"):
        print("  SSO: company-admin, circl-analyst — choose Sign in with SSO at the same login URL")
    print("  Current Bearings accounts (own/retained passwords):")
    code = (
        "from docker.dev.entrypoint import environment; environment(); import django; django.setup(); "
        "from django.contrib.auth import get_user_model; import json; "
        "print(json.dumps(list(get_user_model().objects"
        ".order_by('username').values('username','is_active'))))"
    )
    try:
        result = run(
            base + ["exec", "-T", "web", "/app/.venv/bin/python", "-c", code], capture_output=True, text=True
        )
        users = json.loads(result.stdout)
        for user in users:
            print(
                "    "
                + json.dumps(user["username"], ensure_ascii=True)
                + (" — active" if user["is_active"] else " — inactive")
            )
        if not users:
            print("    none found")
    except (subprocess.CalledProcessError, ValueError, KeyError, TypeError):
        print("    unavailable; current account state could not be read (no account changed)")
    for label, path in [
        ("Workspace", "/applications/"),
        ("Infrastructure overview", "/"),
        ("National overview (CIRCL/platform)", "/circl/"),
        ("Registration", "/register/"),
        ("Registrations", "/operator/registrations/"),
        ("Awaiting email / activation override", "/operator/registrations/?status=awaiting_email"),
        ("Django admin (platform-admin)", "/admin/"),
        ("Registration backend", "/admin/portal/infrastructureregistration/"),
        ("Local mail outbox (platform-admin)", "/operator/service-mail/"),
        ("Inventory", "/inventory/"),
    ]:
        print(f"  {label}: {url(bearings, path)}")
    if state.get("sso"):
        print("  HTTP development listener (plain HTTP): " + url(http, "/accounts/login/"))
    secret(
        "  Generated initial Bearings / NetBox / SSO user password:",
        "web",
        "/run/bearings/secrets/demo_password",
    )

    if state["mode"] == "bundled":
        netbox = origin("netbox-tls", 443)
        print("\nNETBOX")
        print("  Local login: " + url(netbox, "/login/"))
        print("  netbox-admin — local administrator; generated password shown above")
        if state.get("sso"):
            print("  company-admin, circl-analyst — OpenID Connect button; scoped read-only human access")
        print("  Inventory: " + url(netbox, "/dcim/devices/"))
    else:
        print("\nEXTERNAL NETBOX — operator-managed accounts/passwords, unchanged")
        try:
            config = json.loads(external_config.read_text())
            external = config.get("browser_url") or config["base_url"]
            parsed = urlsplit(external)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError()
            print("  URL: " + external)
        except (OSError, ValueError, KeyError, TypeError):
            print("  URL unavailable; inspect the private external configuration")

    if state.get("sso"):
        keycloak = origin("netbox-tls", 444)
        print("\nKEYCLOAK")
        print("  SSO users: company-admin, circl-analyst; unassigned-demo (intentional application denial)")
        print("  User account console: " + url(keycloak, "/realms/bearings-lab/account/"))
        print("  Realm issuer: " + url(keycloak, "/realms/bearings-lab"))
        print("  sso-admin — local bootstrap administrator (separate initial password below)")
        print("  Admin console: " + url(keycloak, "/admin/master/console/"))
        secret(
            "  Generated initial Keycloak sso-admin password:",
            "keycloak",
            "/run/credentials/bootstrap_password",
        )

    if state.get("flowintel"):
        flowintel = origin("flowintel-tls", 443)
        print("\nFLOWINTEL")
        print("  Login: " + url(flowintel, "/account/login"))
        print("  platform-admin@example.com — Local account / administrator recovery form")
        print(
            "  circl-analyst@example.com — local form"
            + ("; or circl-analyst via SSO" if state.get("sso") else "")
        )
        print("  Company accounts have no FlowIntel access")
        secret("  Generated initial FlowIntel password:", "flowintel", "/run/flowintel/demo_password")

    if state.get("rt"):
        rt, recovery = origin("netbox-tls", 445), origin("netbox-tls", 446)
        print("\nRT / RTIR")
        print("  RT: " + url(rt))
        print(
            "  company-admin, circl-analyst — "
            + ("SSO at the RT URL" if state.get("sso") else "local RT login")
        )
        print("  Local recovery login: " + url(recovery, "/NoAuth/Login.html"))
        print("  root, company-admin, circl-analyst — local RT accounts; scoped rights remain enforced")
        if state.get("rtir"):
            print("  RTIR (circl-analyst): " + url(rt, "/RTIR/"))
            print("  RTIR local recovery (root): " + url(recovery, "/RTIR/"))
        secret("  Generated initial RT / RTIR password:", "rt", "/run/rt/demo_password")
    print(
        "\nOnly selected profiles are listed. Trust the lab CA before using HTTPS. No API tokens/client secrets are displayed."
    )
