"""Guarded, verified-TLS browser proof for the synthetic RT local-password path."""

import http.cookiejar
from html import unescape
import json
import ssl
from urllib.error import HTTPError
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import (
    build_opener,
    ProxyHandler,
    HTTPSHandler,
    HTTPCookieProcessor,
    HTTPRedirectHandler,
    Request,
)

from scripts import dev
from scripts.sso_smoke import RTLocalLoginForm


def main():
    state = dev.active()
    if state["mode"] != "bundled" or not state.get("rt") or state.get("sso"):
        raise SystemExit("Local RT browser proof requires the explicitly enabled bundled RT lab with SSO off")
    base = dev.compose(state["mode"], state["project"], state.get("flowintel", False), False, True)

    def read(name):
        return dev.run(
            base + ["exec", "-T", "web", "cat", "/run/bearings/" + name], capture_output=True, text=True
        ).stdout.strip()

    data = json.loads(read("secrets/rt.json"))
    parsed = urlsplit(data["browser_url"])
    if (
        data["base_url"] != "https://rt.bearings.test"
        or parsed.scheme != "https"
        or parsed.hostname != "localhost"
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise SystemExit("Local RT smoke refuses modified/non-local source identities")
    tls = ssl.create_default_context(cadata=read("trust/netbox-ca.crt"))
    password = read("secrets/demo_password")

    class LocalRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            target = urlsplit(newurl)
            if target.scheme != parsed.scheme or target.netloc != parsed.netloc:
                raise RuntimeError("Unexpected local RT redirect")
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    try:
        for kind, username in [("company", "company-admin"), ("circl", "circl-analyst")]:
            browser = build_opener(
                ProxyHandler({}),
                HTTPSHandler(context=tls),
                HTTPCookieProcessor(http.cookiejar.CookieJar()),
                LocalRedirect(),
            )
            login = data["browser_url"] + "/NoAuth/Login.html"
            with browser.open(login, timeout=15) as response:
                form = RTLocalLoginForm()
                form.feed(response.read(2_000_000).decode())
            if not form.action:
                raise RuntimeError("Expected RT local login")
            target = urljoin(login, form.action)
            if urlsplit(target).scheme != "https" or urlsplit(target).netloc != parsed.netloc:
                raise RuntimeError("Unexpected login destination")
            form.fields.update(user=username, **{"pass": password})
            with browser.open(
                Request(target, data=urlencode(form.fields).encode(), headers={"Referer": login}), timeout=15
            ) as response:
                response.read(2_000_000)
            with browser.open(
                data["browser_url"] + "/Ticket/Display.html?id=" + str(data["probe_tickets"][kind]),
                timeout=15,
            ) as response:
                assert "Bearings " + kind + " isolation probe (SYNTHETIC)" in unescape(
                    response.read(2_000_000).decode()
                )
            other = "circl" if kind == "company" else "company"
            try:
                with browser.open(
                    data["browser_url"] + "/Ticket/Display.html?id=" + str(data["probe_tickets"][other]),
                    timeout=15,
                ) as response:
                    body = unescape(response.read(2_000_000).decode())
                    assert "Bearings " + other + " isolation probe (SYNTHETIC)" not in body
                    assert "permission" in body.lower() or "could not" in body.lower()
            except HTTPError as error:
                assert error.code in {403, 404}
    except Exception:
        raise SystemExit(
            "Local RT browser proof failed; check private credentials and current queue policies. No sensitive response was printed."
        ) from None
    print(
        "Verified real RT company/CIRCL local-password login, own ticket access and foreign-queue denial with TLS verification. Credentials and roles were preserved."
    )
