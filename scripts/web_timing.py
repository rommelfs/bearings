"""Measure real local lab HTTP/HTTPS/SSO paths; never print credentials or response bodies."""

import http.cookiejar
import json
import re
import ssl
from time import perf_counter, sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import (
    build_opener,
    HTTPCookieProcessor,
    HTTPSHandler,
    HTTPRedirectHandler,
    ProxyHandler,
    Request,
)
from scripts import dev
from scripts.sso_smoke import LoginForm

MAX_BODY = 2_000_000


def origins(manifest, canvas_port):
    """Accept only the fixed synthetic issuer and loopback lab ports."""
    ports = manifest["ports"]
    numbers = [ports["bearings"], ports["sso"], canvas_port]
    if any(type(port) is not int or not 1 <= port <= 65535 for port in numbers):
        raise ValueError("Invalid local lab ports")
    issuer = f"https://localhost:{ports['sso']}/realms/bearings-lab"
    if manifest["issuer"] != issuer:
        raise ValueError("Unrecognized local lab issuer")
    return f"http://localhost:{ports['bearings']}", f"https://localhost:{canvas_port}", issuer


class LocalRedirect(HTTPRedirectHandler):
    def __init__(self, urls):
        self.allowed = {(urlsplit(url).scheme, urlsplit(url).netloc) for url in urls}

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urlsplit(newurl)
        if (target.scheme, target.netloc) not in self.allowed:
            raise ValueError("Unexpected redirect origin")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(browser, request):
    started = perf_counter()
    with browser.open(request, timeout=20) as response:
        received = perf_counter()
        body = response.read(MAX_BODY + 1)
        if len(body) > MAX_BODY:
            raise ValueError("Oversized lab response")
        timing = {
            name: float(duration)
            for name, duration in re.findall(
                r"([a-z]+);dur=(\d+(?:\.\d+)?)", response.headers.get("Server-Timing", "")
            )
            if name
            in {
                "national",
                "nationalshell",
                "mapdatabase",
                "nationalcounts",
                "nationalversions",
                "nationalvulns",
                "nationaltrend",
                "overview",
                "registration",
                "session",
                "django",
                "database",
                "dbmax",
                "scope",
                "companies",
                "priority",
                "render",
                "ranking",
                "issuepreviews",
                "legacypreviews",
            }
        }
        return (
            body.decode(),
            urlsplit(response.url).path,
            {
                "status": response.status,
                "ttfb_ms": round((received - started) * 1000, 1),
                "total_ms": round((perf_counter() - started) * 1000, 1),
                "server_ms": timing,
            },
        )


def main(username="company-admin", *, national=False, registration=False):
    if registration and national:
        raise SystemExit("Choose registration or national timing, not both")
    state = dev.active()
    if state["mode"] != "bundled" or not state.get("sso"):
        raise SystemExit(
            "web-timing requires the bundled synthetic SSO lab; external environments are refused"
        )
    if username not in {"company-admin", "circl-analyst"}:
        raise SystemExit("Use an existing synthetic lab identity")
    base = dev.compose(
        state["mode"],
        state["project"],
        state.get("flowintel", False),
        True,
        state.get("rt", False),
        state.get("rtir", False),
    )

    def read(path):
        return dev.run(
            base + ["exec", "-T", "web", "cat", "/run/bearings/" + path],
            capture_output=True,
            text=True,
        ).stdout.strip()

    cookies = http.cookiejar.CookieJar()
    browser = None
    app = None
    phase = "configuration"
    try:
        manifest = json.loads(read("secrets/oidc-lab.json"))
        canvas_port = int(
            dev.run(
                base + ["exec", "-T", "web", "printenv", "BEARINGS_CANVAS_PORT"],
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
        direct, app, issuer = origins(manifest, canvas_port)
        tls = ssl.create_default_context(cadata=read("trust/netbox-ca.crt"))
        browser = build_opener(
            ProxyHandler({}),
            HTTPSHandler(context=tls),
            HTTPCookieProcessor(cookies),
            LocalRedirect([direct, app, issuer]),
        )
        for phase, origin in [("http_login", direct), ("https_login", app)]:
            body, _, metrics = fetch(browser, origin + "/accounts/login/")
            print(json.dumps({"phase": phase, **metrics}), flush=True)
        if registration:
            for origin, label in [(direct, "http"), (app, "https")]:
                for repeat in range(2):
                    phase = "public_" + label + "_registration"
                    _, public_path, metrics = fetch(browser, origin + "/register/")
                    print(
                        json.dumps({"phase": phase, "sample": repeat + 1, "path": public_path, **metrics}),
                        flush=True,
                    )
        phase = "sso_login"
        form = LoginForm(app_form=True)
        form.feed(body)
        if form.action != "/oauth/login/oidc/":
            raise ValueError("Expected local SSO form")
        if registration:
            form.fields["next"] = "/register/"
        body, _, _ = fetch(
            browser,
            Request(
                app + form.action,
                data=urlencode(form.fields).encode(),
                headers={"Referer": app + "/accounts/login/"},
            ),
        )
        form = LoginForm()
        form.feed(body)
        target = urlsplit(form.action or "")
        approved = urlsplit(issuer)
        if (target.scheme, target.netloc) != (approved.scheme, approved.netloc) or not target.path.startswith(
            approved.path + "/login-actions/"
        ):
            raise ValueError("Expected local identity-provider form")
        form.fields.update(username=username, password=read("secrets/demo_password"))
        body, path, _ = fetch(browser, Request(form.action, data=urlencode(form.fields).encode()))
        if path != ("/register/" if registration else "/") or "Sign out here" not in body:
            raise ValueError("SSO login did not reach the expected authenticated page")
        paths = [("/", "overview"), ("/applications/", "applications")]
        if registration:
            paths = [("/register/", "authenticated_registration")]
        if national:
            paths = [
                ("/circl/", "national"),
                *[
                    (f"/circl/panels/{part}/", "national" + part)
                    for part in ["summary", "problems", "versions", "activity"]
                ],
                ("/circl/map/data/", "nationalmap"),
                ("/applications/", "applications"),
            ]
        for path, phase in paths:
            for repeat in range(
                2 if phase in {"national", "overview", "applications", "authenticated_registration"} else 1
            ):
                if repeat and not registration:
                    sleep(6)
                started = perf_counter()
                try:
                    _, final_path, metrics = fetch(browser, app + path)
                except HTTPError as error:
                    print(
                        json.dumps(
                            {
                                "phase": phase,
                                "sample": repeat + 1,
                                "status": error.code,
                                "error": "http_error",
                                "server_ms": {
                                    name: float(value)
                                    for name, value in re.findall(
                                        r"([a-z]+);dur=(\d+(?:\.\d+)?)",
                                        error.headers.get("Server-Timing", ""),
                                    )
                                    if name
                                    in {
                                        "national",
                                        "database",
                                        "dbmax",
                                        "nationalcounts",
                                        "nationalversions",
                                        "nationalvulns",
                                        "nationaltrend",
                                    }
                                },
                                "total_ms": round((perf_counter() - started) * 1000, 1),
                            }
                        ),
                        flush=True,
                    )
                    continue
                except (URLError, OSError):
                    print(
                        json.dumps(
                            {
                                "phase": phase,
                                "sample": repeat + 1,
                                "error": "network_or_timeout",
                                "timeout_seconds": 20,
                                "total_ms": round((perf_counter() - started) * 1000, 1),
                            }
                        ),
                        flush=True,
                    )
                    continue
                if registration:
                    metrics["path"] = final_path
                if final_path != path:
                    raise ValueError("Unexpected authentication redirect")
                print(json.dumps({"phase": phase, "sample": repeat + 1, **metrics}), flush=True)

    except (HTTPError, URLError, OSError, ValueError, KeyError, TypeError) as error:
        print(
            json.dumps(
                {
                    "phase": phase,
                    "error": "http_error" if isinstance(error, HTTPError) else "request_or_validation_error",
                    **({"status": error.code} if isinstance(error, HTTPError) else {}),
                }
            ),
            flush=True,
        )
        # Exceptions/HTTP bodies can contain codes, passwords or provider details.
        raise SystemExit(
            f"web-timing failed during {phase}; check local service health and lab login"
        ) from None
    finally:
        if browser and app:
            csrf = next((cookie.value for cookie in cookies if cookie.name == "csrftoken"), None)
            if csrf:
                try:
                    fetch(
                        browser,
                        Request(
                            app + "/accounts/logout/",
                            data=urlencode({"csrfmiddlewaretoken": csrf}).encode(),
                            headers={"Referer": app + "/"},
                        ),
                    )
                except (HTTPError, URLError, OSError, ValueError):
                    pass
        cookies.clear()
