"""Real Chromium/WebKit form/CSP/SSO checks, guarded bundled synthetic lab only.

Optional test dependency: Playwright 1.62.0 and the selected browser runtime.
Self-signed browser TLS is allowed only in a fresh loopback-only fixture context;
the FlowIntel server's own OIDC requests retain verified TLS. No credentials,
cookies, codes, callback URLs or page/console bodies are printed.
"""

import argparse
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import dev  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", choices=("chromium", "webkit"), default="chromium")
    parser.add_argument("--chromium-executable")
    args = parser.parse_args()
    state = dev.active()
    if state["mode"] != "bundled" or not state.get("sso") or not state.get("flowintel"):
        raise SystemExit("Real browser check requires the bundled synthetic FlowIntel/SSO lab")
    base = dev.compose(
        state["mode"], state["project"], True, True, state.get("rt", False), state.get("rtir", False)
    )

    def read(name):
        return dev.run(
            base + ["exec", "-T", "web", "cat", "/run/bearings/" + name], capture_output=True, text=True
        ).stdout.strip()

    connections = json.loads(read("secrets/connections.json"))
    manifest = json.loads(read("secrets/oidc-lab.json"))
    flow = json.loads(read("secrets/flowintel.json"))
    if connections["mode"] != "bundled" or flow["base_url"] != "https://flowintel.bearings.test":
        raise SystemExit("Browser check refuses external/modified source identities")
    origin = flow["browser_url"]
    issuer = manifest["issuer"]
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "localhost"
        or not parsed.port
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise SystemExit("Browser check refuses a non-loopback FlowIntel origin")
    if issuer != f"https://localhost:{manifest['ports']['sso']}/realms/bearings-lab":
        raise SystemExit("Browser check refuses an unexpected IdP")
    allowed = {(urlsplit(url).scheme, urlsplit(url).netloc) for url in (origin, issuer)}
    password = read("secrets/demo_password")
    phase = "browser startup"
    try:
        with sync_playwright() as playwright:
            launch = {"headless": True}
            if args.browser == "chromium":
                launch["args"] = ["--no-sandbox"]
                if args.chromium_executable:
                    launch["executable_path"] = args.chromium_executable
            browser = getattr(playwright, args.browser).launch(**launch)
            try:
                for legacy in (True, False):
                    phase = "legacy CSP rejection" if legacy else "complete SSO sign-in"
                    context = browser.new_context(ignore_https_errors=True)
                    blocked, errors = [], []

                    def guard(route):
                        url = urlsplit(route.request.url)
                        if (url.scheme, url.netloc) not in allowed:
                            blocked.append(True)
                            route.abort()
                        elif (
                            legacy
                            and route.request.method == "GET"
                            and route.request.url == origin + "/account/login"
                        ):
                            response = route.fetch()
                            headers = dict(response.headers)
                            parts = [
                                part.strip()
                                for part in headers["content-security-policy"].split(";")
                                if part.strip()
                            ]
                            headers["content-security-policy"] = "; ".join(
                                "form-action 'self'" if part.startswith("form-action ") else part
                                for part in parts
                            )
                            route.fulfill(response=response, headers=headers)
                        else:
                            route.continue_()

                    context.route("**/*", guard)
                    page = context.new_page()
                    page.on(
                        "console",
                        lambda message: errors.append(message.text) if message.type == "error" else None,
                    )
                    try:
                        page.goto(origin + "/account/login")
                        page.get_by_role("button", name="Sign in with SSO", exact=True).click()
                        if legacy:
                            page.wait_for_timeout(600)
                            assert page.url == origin + "/account/login"
                            assert any("form-action" in message for message in errors)
                        else:
                            page.wait_for_url(
                                lambda url: urlsplit(url).netloc == urlsplit(issuer).netloc, timeout=15000
                            )
                            page.locator("#username").fill("circl-analyst")
                            page.locator("#password").fill(password)
                            page.locator("#kc-login").click()
                            page.wait_for_url(origin + "/", timeout=20000)
                            assert not any("form-action" in message for message in errors)
                        assert not blocked
                    finally:
                        context.close()
            finally:
                browser.close()
    except Exception:
        raise RuntimeError(
            f"{args.browser} FlowIntel browser check failed at {phase}; sensitive details suppressed"
        ) from None
    print(
        json.dumps(
            {
                "engine": args.browser,
                "legacy_form_action_block_reproduced": True,
                "flowintel_sso_login": True,
                "external_requests": False,
            }
        )
    )


if __name__ == "__main__":
    main()
