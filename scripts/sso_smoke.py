"""Standard-library, verified-TLS OIDC browser-flow smoke against the synthetic lab only.

No codes, cookies, passwords, tokens or response bodies are printed.
"""

import http.cookiejar
from html.parser import HTMLParser
import json
import ssl
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit, urljoin
from urllib.request import (
    build_opener,
    HTTPCookieProcessor,
    HTTPSHandler,
    ProxyHandler,
    HTTPRedirectHandler,
    Request,
)
from scripts import dev


class LoginForm(HTMLParser):
    def __init__(self, app_form=False):
        super().__init__()
        self.app_form = app_form
        self.action, self.fields, self.active = None, {}, False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form" and (
            attrs.get("id") == "kc-form-login"
            or (
                self.app_form
                and any(
                    path in attrs.get("action", "")
                    for path in ["/oauth/begin/oidc/", "/oauth/login/oidc/", "/bearings-sso/login"]
                )
            )
        ):
            self.action, self.active = attrs.get("action"), True
        if tag == "input" and self.active and attrs.get("name") and attrs.get("type") == "hidden":
            self.fields[attrs["name"]] = attrs.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form":
            self.active = False


def main():
    state = dev.active()
    if state["mode"] != "bundled" or not state.get("sso"):
        raise SystemExit("SSO smoke is restricted to the explicitly enabled bundled synthetic lab")
    base = dev.compose(state["mode"], state["project"], state.get("flowintel", False), True)

    def read(name):
        return dev.run(
            base + ["exec", "-T", "web", "cat", "/run/bearings/" + name], capture_output=True, text=True
        ).stdout.strip()

    manifest = json.loads(read("secrets/oidc-lab.json"))
    connections = json.loads(read("secrets/connections.json"))
    if connections["mode"] != "bundled" or any(
        item["base_url"] != "https://netbox.bearings.test" for item in connections["connections"]
    ):
        raise SystemExit("SSO smoke refuses modified or external source identities")
    ports = manifest["ports"]
    app, netbox, issuer = (
        f"http://localhost:{ports['bearings']}",
        f"https://localhost:{ports['netbox']}",
        manifest["issuer"],
    )
    if issuer != f"https://localhost:{ports['sso']}/realms/bearings-lab":
        raise SystemExit("SSO smoke refuses an unrecognized issuer")
    allowed = {(urlsplit(url).scheme, urlsplit(url).netloc) for url in [app, netbox, issuer]}
    flow = None
    if state.get("flowintel"):
        flow = json.loads(read("secrets/flowintel.json"))["browser_url"]
        parsed = urlsplit(flow)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "localhost"
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise SystemExit("SSO smoke refuses non-local FlowIntel")
        allowed.add((parsed.scheme, parsed.netloc))
    tls = ssl.create_default_context(cadata=read("trust/netbox-ca.crt"))
    password = read("secrets/demo_password")

    class LocalRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            target = urlsplit(newurl)
            if (target.scheme, target.netloc) not in allowed:
                raise RuntimeError("Unexpected redirect origin")
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    def client():
        return build_opener(
            ProxyHandler({}),
            HTTPSHandler(context=tls),
            HTTPCookieProcessor(http.cookiejar.CookieJar()),
            LocalRedirect(),
        )

    def get(browser, url):
        with browser.open(
            Request(url, headers={"Accept": "text/html,application/json"}), timeout=15
        ) as response:
            body = response.read(2_000_001)
            if len(body) > 2_000_000:
                raise RuntimeError("Oversized smoke response")
            return response.url, body.decode()

    def sign_in(browser, username):
        _, body = get(browser, app + "/accounts/login/")
        begin_form = LoginForm(app_form=True)
        begin_form.feed(body)
        if not begin_form.action or begin_form.action != "/oauth/login/oidc/":
            raise RuntimeError("Expected the application's SSO initiation form")
        with browser.open(
            Request(
                app + begin_form.action,
                data=urlencode(begin_form.fields).encode(),
                headers={"Referer": app + "/accounts/login/"},
            ),
            timeout=15,
        ) as response:
            body = response.read(2_000_000).decode()
        form = LoginForm()
        form.feed(body)
        if not form.action or not form.action.startswith(issuer + "/login-actions/"):
            raise RuntimeError("Expected a scoped IdP login form")
        form.fields.update(username=username, password=password)
        with browser.open(Request(form.action, data=urlencode(form.fields).encode()), timeout=15) as response:
            return response.url, response.read(2_000_000).decode()

    def flow_sign_in(browser):
        _, body = get(browser, flow + "/account/login")
        form = LoginForm(app_form=True)
        form.feed(body)
        assert form.action == "/bearings-sso/login"
        with browser.open(
            Request(
                flow + form.action,
                data=urlencode(form.fields).encode(),
                headers={"Referer": flow + "/account/login"},
            ),
            timeout=15,
        ) as response:
            return response.url, response.read(2_000_000).decode()

    stage = "company authentication"
    try:
        company = client()
        url, body = sign_in(company, "company-admin")
        assert url.startswith(app + "/") and "/accounts/login/" not in url and "company-admin" in body
        stage = "shared NetBox authentication"
        url, body = get(company, netbox + "/login/")
        form = LoginForm(app_form=True)
        form.feed(body)
        assert form.action and form.action.startswith("/oauth/begin/oidc/")
        with company.open(
            Request(
                urljoin(netbox, form.action),
                data=urlencode(form.fields).encode(),
                headers={"Accept": "text/html", "Referer": netbox + "/login/"},
            ),
            timeout=15,
        ) as response:
            url, body = response.url, response.read(2_000_000).decode()
        assert url.startswith(netbox + "/") and "/login/" not in url and "sso-company-admin" in body
        stage = "company NetBox scope"
        ro = next(item for item in connections["connections"] if item["access_mode"] == "read_only")
        rw = next(item for item in connections["connections"] if item["access_mode"] == "read_write")
        own = next(item for item in rw["assets"] if item["object_type"] == "dcim.device")["external_id"]
        foreign = next(item for item in ro["assets"] if item["object_type"] == "dcim.device")["external_id"]
        get(company, netbox + f"/api/dcim/devices/{own}/")
        try:
            get(company, netbox + f"/api/dcim/devices/{foreign}/")
            raise AssertionError("Foreign inventory must be denied")
        except HTTPError as exc:
            assert exc.code in {403, 404}
        stage = "unapproved identity denial"
        url, body = sign_in(client(), "unassigned-demo")
        assert url.startswith(app + "/accounts/login/") and "SSO sign-in failed" in body
        if flow:
            stage = "company FlowIntel denial"
            url, body = flow_sign_in(company)
            assert url.startswith(flow + "/account/login") and "SSO sign-in failed" in body
            stage = "shared CIRCL FlowIntel authentication"
            circl = client()
            sign_in(circl, "circl-analyst")
            url, _ = flow_sign_in(circl)
            assert url.startswith(flow + "/") and "/account/login" not in url
            _, body = get(circl, flow + "/account")
            assert "circl-analyst@example.com" in body
    except Exception:
        raise SystemExit(
            f"SSO smoke failed at {stage}. Check service health and approved local identity bindings; no sensitive response was printed."
        ) from None
    print(
        "Verified real Keycloak OIDC login, one company password prompt across Bearings and NetBox, scoped read-only NetBox access, foreign-tenant denial and unapproved identity denial. TLS verified; no API keys used or accounts/roles created by sign-in."
    )
    if flow:
        print(
            "Also verified CIRCL FlowIntel sign-in using the same IdP session without another password prompt, and company FlowIntel denial."
        )
