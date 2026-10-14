"""Local HTTP server (browser mode): serves the frontend (web/) and the JSON API of api.py."""
from __future__ import annotations

import json
import re
import secrets
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from .api import route
from .config import APP

# React frontend build (frontend/ folder, built with: python start.py)
WEB_DIR = Path(__file__).parent / "web"
# only "/name.ext" or "/assets/name.ext": no "..", no arbitrary subfolders
STATIC_RE = re.compile(r"^/(?:assets/)?[\w-]+(?:\.[\w-]+)+$")
CTYPES = {
    ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml", ".woff2": "font/woff2", ".woff": "font/woff", ".png": "image/png",
}
NO_BUILD = ("<!doctype html><meta charset=utf-8><title>DupFinder</title>"
            "<p style='font:15px sans-serif;padding:30px'>The frontend is not built. "
            "Start DupFinder with <code>python start.py</code>, which builds the React interface and starts the server.</p>")

TOKEN = secrets.token_urlsafe(24)
ALLOWED_HOSTS: set[str] = set()


class Handler(BaseHTTPRequestHandler):
    server_version = APP

    def log_message(self, *args) -> None:  # silence the per-request log
        pass

    def _send(self, code: int, body, ctype: str = "application/json; charset=utf-8") -> None:
        if not isinstance(body, (bytes, bytearray)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _host_ok(self) -> bool:
        # protects against "DNS rebinding" attacks: only accepts requests addressed to localhost
        return self.headers.get("Host", "") in ALLOWED_HOSTS

    def _authorized(self) -> bool:
        return self._host_ok() and secrets.compare_digest(self.headers.get("X-Token", ""), TOKEN)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/":
            if not self._host_ok():
                return self._send(403, {"error": "Host not allowed"})
            try:
                html = (WEB_DIR / "index.html").read_text(encoding="utf-8").replace("__TOKEN__", TOKEN)
            except OSError:
                return self._send(503, NO_BUILD.encode("utf-8"), "text/html; charset=utf-8")
            return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
        if STATIC_RE.match(path) and path != "/index.html":
            if not self._host_ok():
                return self._send(403, {"error": "Host not allowed"})
            f = WEB_DIR / path[1:]
            if not f.is_file():
                return self._send(404, {"error": "Not found"})
            return self._send(200, f.read_bytes(), CTYPES.get(f.suffix, "application/octet-stream"))
        if not self._authorized():
            return self._send(403, {"error": "Unauthorized"})
        self._send(*route("GET", self.path))

    def do_POST(self) -> None:
        if not self._authorized():
            return self._send(403, {"error": "Unauthorized"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._send(400, {"error": "Invalid request"})
        if not isinstance(data, dict):
            return self._send(400, {"error": "Invalid request"})
        self._send(*route("POST", self.path, data))
