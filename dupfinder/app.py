"""Desktop app: the same React interface in a native window (pywebview: WebView2 on Windows,
WebKit on macOS, GTK/Qt on Linux). The interface talks to Python through the pywebview
bridge (window.pywebview.api), so no HTTP API is exposed at all."""
from __future__ import annotations

import base64
from pathlib import Path

from . import api
from .config import APP

WEB_DIR = Path(__file__).parent / "web"


class Bridge:
    """Methods called from JavaScript. Attributes starting with _ are not exposed."""

    def __init__(self) -> None:
        self._window = None

    def call(self, method: str, path: str, body=None) -> dict:
        code, data, ctype = api.route(method, path, body if isinstance(body, dict) else None)
        if isinstance(data, (bytes, bytearray)):
            return {"status": code, "b64": base64.b64encode(data).decode("ascii"), "ctype": ctype}
        return {"status": code, "json": data}

    def pick_folder(self, start: str = "") -> str:
        import webview
        r = self._window.create_file_dialog(webview.FileDialog.FOLDER, directory=start or "")
        return r[0] if r else ""

    def save_text(self, filename: str, text: str) -> str:
        """Asks where to save, writes the file (UTF-8 with BOM, so Excel reads accents) and returns its path."""
        import webview
        r = self._window.create_file_dialog(webview.FileDialog.SAVE, save_filename=filename)
        if not r:
            return ""
        path = r if isinstance(r, str) else r[0]
        with open(path, "w", encoding="utf-8-sig", newline="") as fh:
            fh.write(text)
        return path


def available() -> bool:
    try:
        import webview  # noqa: F401
        return True
    except ImportError:
        return False


def run(debug: bool = False) -> None:
    import webview
    if not (WEB_DIR / "index.html").is_file():
        raise SystemExit("The interface is not built: run python start.py (it needs Node.js) "
                         "or use a packaged DupFinder.")
    api.MODE["app"] = True
    bridge = Bridge()
    window = webview.create_window(
        APP, url=str(WEB_DIR / "index.html"), js_api=bridge, width=1440, height=900,
        min_size=(980, 620), background_color="#0f131c", text_select=True)
    bridge._window = window
    # the built files are served by pywebview's own loopback static-file server (the build uses
    # absolute /assets/ paths, which file:// cannot resolve); the API never goes through it
    # the "DupFinderApp" user agent tells the interface to use the bridge instead of HTTP
    webview.start(debug=debug, http_server=True, private_mode=False,
                  user_agent="Mozilla/5.0 (DupFinderApp) AppleWebKit/537.36 (KHTML, like Gecko)",
                  storage_path=str(api.config.DATA_DIR / "webview"))
    api.SCANNER.stop()

