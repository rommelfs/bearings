#!/usr/bin/env python3
"""Build and serve the project website on loopback, independent of the caller's directory."""

import argparse
import errno
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
import webbrowser

ROOT = Path(__file__).resolve().parent


def main(argv=None, *, open_browser=False):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8050)
    parser.add_argument("--registration-url", default="https://localhost:9441/register/")
    parser.add_argument("--language", choices=("en", "de", "fr", "lb"), default="en")
    parser.add_argument("--open", action=argparse.BooleanOptionalAction, default=open_browser)
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("Port must be between 0 and 65535")
    try:
        subprocess.run(
            [sys.executable, str(ROOT / "build.py"), "--registration-url", args.registration_url],
            check=True,
        )
    except subprocess.CalledProcessError:
        parser.exit(1, "Website build failed; no preview server was started.\n")
    handler = partial(SimpleHTTPRequestHandler, directory=str(ROOT / "dist"))
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    except OSError as error:
        if error.errno == errno.EADDRINUSE:
            parser.exit(
                1,
                f"Port {args.port} is already in use. Stop the previous server with Ctrl+C, "
                "then retry, or choose --port 8051.\n",
            )
        raise
    with server:
        origin = f"http://127.0.0.1:{server.server_port}"
        print(f"Serving generated Bearings website from {ROOT / 'dist'}", flush=True)
        print(f"English: {origin}/  (also /en/)", flush=True)
        print(f"Deutsch: {origin}/de/", flush=True)
        print(f"Français: {origin}/fr/", flush=True)
        print(f"Lëtzebuergesch: {origin}/lb/", flush=True)
        print("Loopback only. Stop with Ctrl+C.", flush=True)
        print("Use HTTP here; registration uses the separate HTTPS lab entrance.", flush=True)
        if args.open:
            try:
                opened = webbrowser.open(f"{origin}/{args.language}/")
            except webbrowser.Error:
                opened = False
            if not opened:
                print(f"Open this address in your browser: {origin}/{args.language}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
