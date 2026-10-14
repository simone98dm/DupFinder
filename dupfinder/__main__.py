"""Command line: python -m dupfinder [folders] [--browser] [--admin] [--port N] [--no-browser] [--no-archives]"""
from __future__ import annotations

import argparse
import sys
import threading
import webbrowser
from http.server import ThreadingHTTPServer

from . import api, app
from .config import APP
from .server import ALLOWED_HOSTS, Handler
from .utils import SEVENZIP, is_admin, relaunch_as_admin


def main() -> None:
    ap = argparse.ArgumentParser(description="Find duplicate files and choose which ones to delete.")
    ap.add_argument("paths", nargs="*", help="folders or drives to scan right away")
    ap.add_argument("--browser", action="store_true",
                    help="use the browser instead of the desktop window (default when pywebview is missing)")
    ap.add_argument("--admin", action="store_true",
                    help="Windows: restart as administrator (to delete protected files)")
    ap.add_argument("--port", type=int, default=8765, help="browser mode: local port (default 8765)")
    ap.add_argument("--no-browser", action="store_true", help="browser mode: do not open the browser")
    ap.add_argument("--no-archives", action="store_true", help="do not scan the contents of zip, 7z and rar")
    ap.add_argument("--debug", action="store_true", help="desktop app: enable the developer tools")
    args = ap.parse_args()

    if args.admin and not is_admin():
        if relaunch_as_admin([a for a in sys.argv if a != "--admin"]):
            return
        print("Warning: could not restart as administrator, continuing normally.")

    api.startup()
    if args.paths:
        api.PREFILL.extend(args.paths)
        try:
            api.SCANNER.start(args.paths, archives=not args.no_archives)
        except ValueError as e:
            print(f"Warning: {e}")

    if not (args.browser or args.no_browser) and app.available():
        app.run(debug=args.debug)
        return
    if not (args.browser or args.no_browser):
        print("pywebview is not installed (pip install pywebview): opening in the browser.")
    serve(args.port, open_browser=not args.no_browser)


def serve(port: int, open_browser: bool) -> None:
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)   # port in use: pick a free one
    port = server.server_address[1]
    ALLOWED_HOSTS.update({f"127.0.0.1:{port}", f"localhost:{port}"})

    url = f"http://127.0.0.1:{port}/"
    print(f"{APP} is running at {url}")
    print(f"7-Zip: {SEVENZIP or 'not found (7z and rar archives will not be scanned)'}")
    print("Press Ctrl+C to quit.")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nClosed.")
    finally:
        api.SCANNER.stop()
        server.server_close()


if __name__ == "__main__":
    main()
