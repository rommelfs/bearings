"""Browser timings for reachable GET links in a loopback-only synthetic Bearings lab."""

import argparse
from collections import Counter, deque
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Thread
from time import perf_counter
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server
from socketserver import ThreadingMixIn


BROWSER_READY = """async () => {
    const pending = '[data-national-panel][aria-busy="true"], [data-host-panel][aria-busy="true"]';
    await new Promise(resolve => {
        const observer = new MutationObserver(check);
        function check() {
            if (!document.querySelector(pending)) {
                observer.disconnect();
                resolve();
            }
        }
        observer.observe(document, {subtree: true, childList: true, attributes: true});
        check();
    });
    await document.fonts.ready;
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
}"""
WAIT_FOR_FRAGMENTS = """() =>
    !document.querySelector('[data-national-panel][aria-busy="true"], [data-host-panel][aria-busy="true"]') &&
    !document.querySelector('[data-map-status]')?.textContent.startsWith('Loading')
"""
EXCLUDED_PATHS = ("/oauth/", "/contacts/verify/", "/register/verify/", "/accounts/logout/", "/admin/logout/")


def destination(base, href, origin):
    url = urlsplit(urljoin(base, href))
    if url.scheme not in {"http", "https"}:
        return None, url.scheme or "other"
    if f"{url.scheme}://{url.netloc}" != origin:
        return None, "external"
    if any(url.path.startswith(path) for path in EXCLUDED_PATHS):
        return None, "session_or_token_action"
    if url.path.startswith(("/static/", "/assets/")) or url.path in {"/style.css", "/site.js"}:
        return None, "static_resource"
    # Return destinations and in-page anchors normally lead to already measured documents.
    params = [
        (k, v) for k, v in parse_qsl(url.query) if k not in {"return_to", "next", "_changelist_filters"}
    ]
    filters = dict(params)
    organization = url.path.startswith("/organizations/") and url.path.count("/") == 3
    # Measure each axis, and leave their Cartesian product to a fixed stress matrix.
    if "sort" in filters and any(
        filters.get(key, default) != default
        for key, default in (
            ("host_filter", "all"),
            ("focus", "all"),
            ("category", "version"),
            ("bucket", "all"),
        )
    ):
        return None, "combined_sort_and_filter"
    if "case" in filters:
        params = [(key, value) for key, value in params if key not in {"sort", "direction"}]
    fragment = ""
    if organization and not params:
        if url.fragment == "hosts":
            fragment = "hosts"
        elif url.fragment in {"inventory", "contacts", "scope", "findings", "organization-administration"}:
            fragment = "inventory"
    return urlunsplit(("", "", url.path, urlencode(sorted(params)), fragment)), None


def route_identity(path):
    # Django signs case identity with a timestamp. Keep a working original URL
    # for navigation while using the payload to recognize the same case again.
    parts = urlsplit(path)
    query = urlencode(
        [
            (key, value.split(":", 1)[0] if key == "case" and value.count(":") == 2 else value)
            for key, value in parse_qsl(parts.query)
        ]
    )
    return parts.path, query, parts.fragment


def is_download(url):
    path = urlsplit(url).path
    return (
        path.startswith(("/downloads/windows/", "/downloads/linux/"))
        and not path.endswith("/")
        or path.endswith(("/import-csv/template/", "/configuration-export/ail/"))
    )


def browser(args):
    from playwright.sync_api import Error, sync_playwright

    origin, roles, seeds = json.load(sys.stdin)
    if urlsplit(origin).hostname != "127.0.0.1":
        raise SystemExit("Only a loopback browser origin is permitted")
    fixed = json.loads(Path(args.replay).read_text())["targets"] if args.replay else {}
    targets, excluded = {}, Counter()
    known_edges = set()
    with (
        sync_playwright() as playwright,
        playwright.chromium.launch(executable_path=args.chromium) as chromium,
        Path(args.output).open("w", buffering=1) as output,
    ):
        for role, cookies in roles.items():
            queue = deque(fixed.get(role, seeds[role]))
            queued = {route_identity(path): path for path in queue}
            targets[role] = []
            context = chromium.new_context(viewport={"width": 1440, "height": 1000})
            context.route(
                "**/*",
                lambda request: (
                    request.continue_() if request.request.url.startswith(origin + "/") else request.abort()
                ),
            )
            context.add_cookies(
                [{"name": key, "value": value, "url": origin} for key, value in cookies.items()]
            )
            page = context.new_page()
            received = []
            errors = []
            page.on("response", lambda response: received.append(response))
            page.on("pageerror", lambda error: errors.append(type(error).__name__))
            while queue:
                url = queue.popleft()
                targets[role].append(url)
                received.clear()
                errors.clear()
                started = perf_counter()
                row = {"role": role, "url": url}
                try:
                    download = is_download(url)
                    if download:
                        response = context.request.get(origin + url, timeout=15000)
                        row.update(status=response.status, downloaded_bytes=len(response.body()))
                    else:
                        # A blank document makes an in-page hash change a real navigation.
                        if page.url.split("#")[0] == (origin + url).split("#")[0]:
                            page.goto("about:blank")
                            started = perf_counter()
                        response = page.goto(origin + url, wait_until="load", timeout=15000)
                        row.update(status=response.status, landed=urlsplit(page.url).path)
                        page.wait_for_function(WAIT_FOR_FRAGMENTS, timeout=16000)
                        page.evaluate(BROWSER_READY)
                        if row["landed"] == "/accounts/login/" and role != "public":
                            row["login_redirect"] = True
                        timing = response.request.timing
                        row["ttfb_ms"] = round(max(timing["responseStart"], 0), 1)
                        row["server_timing"] = response.headers.get("server-timing", "")
                        row["sql_ms"] = response.headers.get("x-scale-sql-ms", "")
                        row["queries"] = response.headers.get("x-scale-queries", "")
                    row["render_ms"] = round((perf_counter() - started) * 1000, 1)
                    row["fragments"] = [
                        {
                            "path": urlsplit(r.url).path,
                            "status": r.status,
                            "ms": round(
                                r.request.timing["responseEnd"] - r.request.timing["requestStart"], 1
                            ),
                            "sql_ms": r.headers.get("x-scale-sql-ms", ""),
                        }
                        for r in received
                        if r.request.resource_type in {"fetch", "xhr"} and r.url.startswith(origin + "/")
                    ]
                    if errors:
                        row["javascript_error"] = True
                    if download or args.replay and not args.verify_links or row["status"] >= 400:
                        continue
                    hrefs = page.locator("a[href], area[href]").evaluate_all(
                        "(links) => links.map(a => a.href)"
                    )
                    for href in hrefs:
                        path, exclusion = destination(page.url, href, origin)
                        if exclusion:
                            excluded[exclusion] += 1
                        elif path:
                            key = route_identity(path)
                            if key not in queued:
                                queued[key] = path
                                if not args.replay:
                                    queue.append(path)
                            known_edges.add((role, url, queued[key]))
                    if len(queued) > args.max_targets:
                        raise SystemExit(f"Coverage guard exceeded for {role}: {len(queued)} targets")
                except Error as error:
                    row.update(
                        error=type(error).__name__, render_ms=round((perf_counter() - started) * 1000, 1)
                    )
                finally:
                    output.write(json.dumps(row) + "\n")
                if len(targets[role]) % 50 == 0:
                    print(f"{role}: {len(targets[role])} measured, {len(queue)} queued", flush=True)
            context.close()
            print(f"{role}: {len(targets[role])} measured", flush=True)
    if not args.replay or args.verify_links:
        manifest = {"targets": targets, "edges": sorted(known_edges), "excluded": dict(excluded)}
        Path(args.output + ".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


class ThreadedServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *args):
        pass


def app(args):
    import django

    if os.environ.get("DJANGO_SETTINGS_MODULE") != "scripts.scale_settings":
        raise SystemExit("Use only scripts.scale_settings and an isolated synthetic database")
    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.contrib.staticfiles.handlers import StaticFilesHandler
    from django.core.wsgi import get_wsgi_application
    from django.db import connection
    from django.test import Client

    if (
        connection.vendor != "postgresql"
        or connection.settings_dict["HOST"] != "127.0.0.1"
        or not connection.settings_dict["NAME"].startswith("bearings_scale_nav_")
        or settings.SSO_ENABLED
    ):
        raise SystemExit("Expected local PostgreSQL navigation fixture with SSO disabled")

    def loopback_only(event, arguments):
        if event == "socket.connect":
            address = arguments[1]
            if isinstance(address, tuple) and address[0] not in {"127.0.0.1", "::1"}:
                raise PermissionError("External connections are disabled for the navigation audit")
        elif event == "socket.getaddrinfo" and arguments[0] not in {None, "localhost", "127.0.0.1", "::1"}:
            raise PermissionError("External DNS is disabled for the navigation audit")

    sys.addaudithook(loopback_only)
    fixture = json.loads(Path(args.fixture).read_text())
    roles = {}
    for role, username in fixture["users"].items():
        client = Client()
        if username:
            user = get_user_model().objects.get(username=username)
            if user.has_usable_password():
                raise SystemExit("Audit accounts must have unusable passwords")
            client.force_login(user)
        roles[role] = {key: value.value for key, value in client.cookies.items()}
    server = make_server(
        "127.0.0.1",
        0,
        StaticFilesHandler(get_wsgi_application()),
        server_class=ThreadedServer,
        handler_class=QuietHandler,
    )
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        command = [
            args.browser_python,
            __file__,
            "--browser",
            "--output",
            args.output,
            "--chromium",
            args.chromium,
        ]
        if args.replay:
            command += ["--replay", args.replay]
        command += ["--max-targets", str(args.max_targets)]
        if args.verify_links:
            command += ["--verify-links"]
        subprocess.run(
            command,
            input=json.dumps([f"http://127.0.0.1:{server.server_port}", roles, fixture["seeds"]]),
            text=True,
            check=True,
        )
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture")
    parser.add_argument(
        "--output", required=True, help="JSONL timing output. Discovery also writes a manifest."
    )
    parser.add_argument("--replay", help="Replay the exact role/URL matrix from a prior discovery manifest.")
    parser.add_argument(
        "--browser-python", default="python3", help="Python executable with Playwright installed."
    )
    parser.add_argument("--chromium", default="/usr/bin/chromium")
    parser.add_argument(
        "--verify-links", action="store_true", help="Inventory links without changing a replay matrix."
    )
    parser.add_argument("--max-targets", type=int, default=2500)
    parser.add_argument("--browser", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.browser and not args.fixture:
        parser.error("--fixture is required")
    (browser if args.browser else app)(args)


if __name__ == "__main__":
    main()
