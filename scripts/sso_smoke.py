"""Standard-library, verified-TLS OIDC browser-flow smoke against the synthetic lab only.

No codes, cookies, passwords, tokens or response bodies are printed.
"""

import http.cookiejar
from html import unescape
from html.parser import HTMLParser
import json
import re
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


class RTLocalLoginForm(LoginForm):
    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "form" and "/NoAuth/Login.html" in values.get("action", ""):
            self.action, self.active = values["action"], True
        if tag == "input" and self.active and values.get("name") and values.get("type") == "hidden":
            self.fields[values["name"]] = values.get("value", "")


class CanvasLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.frames = {}, []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        match = re.fullmatch(r"/applications/(netbox|flowintel|rt|rtir)-[a-f0-9-]+/", values.get("href", ""))
        if tag == "a" and match:
            self.links.setdefault(match[1], values["href"])
        if tag == "iframe":
            self.frames.append(values)


def main():
    state = dev.active()
    if state["mode"] != "bundled" or not state.get("sso"):
        raise SystemExit("SSO smoke is restricted to the explicitly enabled bundled synthetic lab")
    base = dev.compose(
        state["mode"],
        state["project"],
        state.get("flowintel", False),
        True,
        state.get("rt", False),
        state.get("rtir", False),
    )

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
    rt_lab = None
    if state.get("rt"):
        rt_lab = json.loads(read("secrets/rt.json"))
        parsed = urlsplit(rt_lab["browser_url"])
        if (
            parsed.scheme != "https"
            or parsed.hostname != "localhost"
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
            or rt_lab["base_url"] != "https://rt.bearings.test"
        ):
            raise SystemExit("SSO smoke refuses non-local RT")
        allowed.add((parsed.scheme, parsed.netloc))
        recovery = "https://localhost:" + str(rt_lab["recovery_port"])
        allowed.add(("https", urlsplit(recovery).netloc))
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
    canvas_port = int(
        dev.run(
            base + ["exec", "-T", "web", "printenv", "BEARINGS_CANVAS_PORT"], capture_output=True, text=True
        ).stdout.strip()
    )
    canvas = f"https://localhost:{canvas_port}"
    allowed.add(("https", urlsplit(canvas).netloc))
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
        assert "Single sign-on" in body and "Local account / administrator recovery" in body
        assert body.index("Sign in with SSO") < body.index("<details")
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
        unassigned = client()
        url, body = sign_in(unassigned, "unassigned-demo")
        assert url.startswith(app + "/accounts/login/") and "SSO sign-in failed" in body
        circl = None
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
        if rt_lab:
            if circl is None:
                circl = client()
                sign_in(circl, "circl-analyst")
            for kind, browser in [("company", company), ("circl", circl)]:
                stage = kind + " shared RT authentication and queue access"
                url, body = get(
                    browser,
                    rt_lab["browser_url"] + "/Ticket/Display.html?id=" + str(rt_lab["probe_tickets"][kind]),
                )
                assert url.startswith(rt_lab["browser_url"] + "/")
                assert "Bearings " + kind + " isolation probe (SYNTHETIC)" in unescape(body)
                other = "circl" if kind == "company" else "company"
                stage = kind + " RT foreign queue denial"
                try:
                    _, body = get(
                        browser,
                        rt_lab["browser_url"]
                        + "/Ticket/Display.html?id="
                        + str(rt_lab["probe_tickets"][other]),
                    )
                    assert "Bearings " + other + " isolation probe (SYNTHETIC)" not in unescape(body)
                    assert "permission" in body.lower() or "could not" in body.lower()
                except HTTPError as exc:
                    assert exc.code in {403, 404}
            if state.get("rtir"):
                stage = "native RTIR synthetic fixture verification"
                code = "from portal.models import RTTicket; import json; print(json.dumps(list(RTTicket.objects.filter(instance__name='bundled-rtir-circl', issue__source_label='Synthetic RTIR exercise', state='linked').values('id','role','remote_id','subject','issue__organization__slug')),default=str))"
                result = dev.run(
                    base
                    + [
                        "exec",
                        "-T",
                        "web",
                        "/app/.venv/bin/python",
                        "docker/dev/entrypoint.py",
                        "manage",
                        "shell",
                        "--no-imports",
                        "-c",
                        code,
                    ],
                    capture_output=True,
                    text=True,
                )
                rows = json.loads(result.stdout)
                assert len(rows) == 4 and sum(row["role"] == "incident" for row in rows) == 1
                for row in rows:
                    stage = "CIRCL native RTIR SSO ticket access"
                    _, body = get(
                        circl, rt_lab["browser_url"] + "/RTIR/Display.html?id=" + str(row["remote_id"])
                    )
                    assert row["subject"] in unescape(body)
                    stage = "company native RTIR ticket denial"
                    try:
                        _, body = get(
                            company, rt_lab["browser_url"] + "/RTIR/Display.html?id=" + str(row["remote_id"])
                        )
                        assert row["subject"] not in unescape(body)
                        assert "permission" in body.lower() or "could not" in body.lower()
                    except HTTPError as exc:
                        assert exc.code in {403, 404}
                parent = next(row for row in rows if row["role"] == "incident")
                stage = "CIRCL Bearings Incident view"
                path = "/organizations/" + parent["issue__organization__slug"] + "/rt/" + parent["id"] + "/"
                _, body = get(circl, app + path)
                assert "Investigations by company and asset" in body
                stage = "company Bearings Incident denial"
                try:
                    get(company, app + path)
                    raise AssertionError("Company must not read aggregate")
                except HTTPError as exc:
                    assert exc.code == 404
            stage = "RT unapproved identity denial"
            try:
                get(unassigned, rt_lab["browser_url"] + "/")
                raise AssertionError("Unapproved RT subject must be denied")
            except HTTPError as exc:
                assert exc.code == 403
            stage = "RT local emergency login"
            local = client()
            _, body = get(local, recovery + "/NoAuth/Login.html")
            form = RTLocalLoginForm()
            form.feed(body)
            assert form.action
            target = urljoin(recovery, form.action)
            assert urlsplit(target).scheme == "https" and urlsplit(target).netloc == urlsplit(recovery).netloc
            form.fields.update(user="root", **{"pass": password})
            with local.open(
                Request(
                    target,
                    data=urlencode(form.fields).encode(),
                    headers={"Referer": recovery + "/NoAuth/Login.html"},
                ),
                timeout=15,
            ) as response:
                response.read(2_000_000)
            url, body = get(local, recovery + "/Admin/Users/index.html")
            assert "/NoAuth/Login.html" not in urlsplit(url).path and "Enoch Root" in body
            stage = "RT recovery does not bypass the SSO entry point"
            _, body = get(local, rt_lab["browser_url"] + "/")
            assert "kc-form-login" in body
        stage = "HTTPS application canvas and scoped directory"
        for role, browser in [("company", company)] + ([("circl", circl)] if circl else []):
            _, body = get(browser, canvas + "/applications/")
            links = CanvasLinks()
            links.feed(body)
            assert "netbox" in links.links
            if role == "company":
                assert not {"flowintel", "rtir"}.intersection(links.links)
            for kind, path in links.links.items():
                stage = role + " " + kind + " canvas policy"
                with browser.open(canvas + path + "?show=1", timeout=15) as response:
                    parser = CanvasLinks()
                    parser.feed(response.read(2_000_000).decode())
                    assert len(parser.frames) == 1
                    frame = parser.frames[0]
                    expected = {
                        "netbox": netbox,
                        "flowintel": flow,
                        "rt": rt_lab["browser_url"] if rt_lab else None,
                        "rtir": rt_lab["browser_url"] if rt_lab else None,
                    }[kind]
                    assert frame["src"] == expected + ("/RTIR/" if kind == "rtir" else "/")
                    assert (
                        frame["sandbox"]
                        == "allow-scripts allow-same-origin allow-forms allow-popups allow-downloads"
                    )
                    assert frame["referrerpolicy"] == "no-referrer"
                    assert "frame-src " + expected + ";" in response.headers["Content-Security-Policy"]
                    assert response.headers["X-Frame-Options"] == "DENY"
                # NetBox requires its explicit SSO button; only the company has used it above.
                if kind != "netbox" or role == "company":
                    with browser.open(frame["src"], timeout=15) as response:
                        response.read(2_000_000)
                        assert (
                            "frame-ancestors 'self' " + canvas in response.headers["Content-Security-Policy"]
                        )
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
    if rt_lab:
        print(
            "Also verified real RT company/CIRCL SSO with existing provider sessions, permitted tickets, foreign-queue/unapproved identity denial and local emergency login."
        )

    if state.get("rtir"):
        print(
            "Also verified CIRCL native RTIR Incident/Investigation browser access through shared SSO and company denial in RTIR and Bearings."
        )
    print(
        "Also verified the HTTPS canvas, company/CIRCL application directory, sandboxed frame destinations and exact native embedding policy; no credentials proxied to the browser."
    )
