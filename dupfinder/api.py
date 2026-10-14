"""The API, independent of the transport: route() is called by the HTTP server
(browser mode) and by the pywebview bridge (desktop app, no network at all)."""
from __future__ import annotations

import json
import os
import sys
import threading
from urllib.parse import parse_qs

from . import config, extract, images, jobs, quarantine
from .catalog import CATALOG, archive_job, restore_job, verify_job
from .config import (DEFAULT_EXCLUDES, IMAGE_EXTS, IS_MAC, IS_WIN, MAX_NEST, PREVIEW_MAX,
                     TEXT_EXTS, WEB_IMAGE_EXTS)
from .scanner import Scanner
from .utils import (SEVENZIP, _send2trash, describe_os_error, is_admin, relaunch_as_admin,
                    reveal_in_file_manager, suggested_roots)
from .watcher import Watcher

SCANNER = Scanner()
WATCHER = Watcher(CATALOG)
PREFILL: list[str] = []
MODE = {"app": False}          # desktop app (pywebview) or browser
CTYPES_IMG = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
              ".bmp": "image/bmp", ".gif": "image/gif"}


class HttpError(Exception):
    def __init__(self, code: int, msg: str) -> None:
        super().__init__(msg)
        self.code = code


# ---------- settings (~/.dupfinder/settings.json) ----------
def load_settings() -> dict:
    try:
        with open(config.DATA_DIR / "settings.json", encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(changes: dict) -> dict:
    s = load_settings()
    s.update(changes)
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = config.DATA_DIR / "settings.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(s, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, config.DATA_DIR / "settings.json")
    return s


def startup() -> None:
    """Restores the last session and the watcher at program start."""
    SCANNER.load_session()
    s = load_settings()
    if s.get("watch_enabled") and s.get("watch_folders"):
        try:
            WATCHER.configure(s["watch_folders"], True)
        except ValueError:
            pass


# ---------- routing ----------
def route(method: str, path: str, data: dict | None = None):
    """Returns (status, body, content type); body is a dict (JSON) or bytes."""
    path, _, qs = path.partition("?")
    q = {k: v[0] for k, v in parse_qs(qs).items()}
    try:
        if method == "GET":
            body = _get(path, q)
        else:
            body = _post(path, data or {})
        if isinstance(body, tuple):                     # (bytes, content type)
            return 200, body[0], body[1]
        return 200, body, "application/json; charset=utf-8"
    except HttpError as e:
        return e.code, {"error": str(e)}, "application/json; charset=utf-8"
    except ValueError as e:
        return 400, {"error": str(e)}, "application/json; charset=utf-8"
    except OSError as e:
        return 500, {"error": describe_os_error(e)}, "application/json; charset=utf-8"
    except Exception as e:  # noqa: BLE001
        return 500, {"error": f"{type(e).__name__}: {e}"}, "application/json; charset=utf-8"


def _get(path: str, q: dict):
    if path == "/api/config":
        return {
            "prefill": PREFILL, "roots": suggested_roots(), "excludes": DEFAULT_EXCLUDES,
            "trash": _send2trash is not None, "quarantine_dir": str(config.QUARANTINE_ROOT),
            "platform": "windows" if IS_WIN else ("mac" if IS_MAC else "linux"),
            "sevenzip": SEVENZIP, "max_nest": MAX_NEST, "pillow": images.available(),
            "admin": is_admin(), "can_elevate": IS_WIN and not is_admin(), "app": MODE["app"],
            "settings": load_settings(),
        }
    if path == "/api/state":
        return SCANNER.status()
    if path == "/api/results":
        return SCANNER.results()
    if path == "/api/job":
        return jobs.status(q.get("kind", ""))
    if path == "/api/catalog":
        return CATALOG.summary()
    if path == "/api/catalog/search":
        return {"results": CATALOG.search(q.get("q", ""))}
    if path == "/api/quarantine":
        return {"sessions": quarantine.sessions()}
    if path == "/api/watch":
        return WATCHER.status(int(q.get("since", 0) or 0))
    if path == "/api/similar":
        return {"groups": images.results(SCANNER)}
    if path == "/api/preview":
        return _preview(q.get("set", "dup"), int(q.get("id", -1)))
    raise HttpError(404, "Not found")


def _post(path: str, d: dict):
    if path == "/api/scan":
        SCANNER.start(d.get("paths", []), d.get("min_size", 1), d.get("excludes"),
                      d.get("skip_system", True), d.get("archives", True))
        return {"ok": True}
    if path == "/api/cancel":
        SCANNER.stop()
        return {"ok": True}
    if path == "/api/delete":
        return SCANNER.delete(d.get("ids", []), d.get("mode", "trash"),
                              bool(d.get("arc_keep")), bool(d.get("similar")))
    if path == "/api/selection":
        SCANNER.set_selection(d.get("session"), d.get("ids", []))
        return {"ok": True}
    if path == "/api/reveal":
        index = SCANNER.sim["index"] if d.get("set") == "sim" else SCANNER.index
        info = index.get(int(d.get("id", -1)))
        if not info:
            raise HttpError(404, "File not found")
        reveal_in_file_manager(info["chain"][0] if info["chain"] else info["path"])
        return {"ok": True}
    if path == "/api/reveal_path":
        p = str(d.get("path", ""))
        if not os.path.exists(p):
            raise HttpError(404, "File not found: it was moved or deleted")
        reveal_in_file_manager(p)
        return {"ok": True}
    if path == "/api/settings":
        return save_settings({k: v for k, v in d.items() if isinstance(k, str)})
    if path == "/api/job/start":
        return _start_job(d)
    if path == "/api/job/cancel":
        jobs.cancel(d.get("kind", ""))
        return {"ok": True}
    if path == "/api/extract/plan":
        return extract.plan(SCANNER, str(d.get("archive", "")), d.get("dest") or None)
    if path == "/api/catalog/forget":
        CATALOG.forget(int(d.get("id", -1)))
        return {"ok": True}
    if path == "/api/quarantine/restore":
        return quarantine.restore(str(d.get("id", "")), d.get("stored"))
    if path == "/api/quarantine/purge":
        return quarantine.purge(str(d.get("id", "")))
    if path == "/api/watch":
        folders, enabled = list(d.get("folders", [])), bool(d.get("enabled"))
        WATCHER.configure(folders, enabled)
        save_settings({"watch_folders": WATCHER.folders, "watch_enabled": WATCHER.enabled})
        return WATCHER.status()
    if path == "/api/admin/restart":
        if not relaunch_as_admin(sys.argv):
            raise ValueError("Elevation was refused or is not available on this system.")
        SCANNER.stop()
        # leave time for the reply to reach the interface, then quit: the new process takes over
        threading.Timer(1.0, lambda: os._exit(0)).start()
        return {"ok": True}
    raise HttpError(404, "Not found")


def _start_job(d: dict):
    kind = d.get("kind")
    if kind == "archive":
        jobs.start(kind, archive_job, CATALOG, list(d.get("sources", [])), str(d.get("dest", "")))
    elif kind == "verify":
        jobs.start(kind, verify_job, CATALOG, d.get("ids") or None)
    elif kind == "restore":
        jobs.start(kind, restore_job, CATALOG, [int(i) for i in d.get("ids", [])], d.get("target") or None)
    elif kind == "extract":
        jobs.start(kind, extract.extract_job, SCANNER, str(d.get("archive", "")), str(d.get("dest", "")),
                   bool(d.get("skip_dups", True)), str(d.get("after", "keep")))
    elif kind == "similar":
        jobs.start(kind, images.similar_job, SCANNER, CATALOG)
    else:
        raise ValueError("Unknown operation.")
    return jobs.status(kind)


def _preview(which: str, fid: int):
    index = SCANNER.sim["index"] if which == "sim" else SCANNER.index
    info = index.get(fid)
    if not info or info["chain"]:
        raise HttpError(404, "No preview for this file")
    p = info["path"]
    ext = os.path.splitext(p)[1].lower()
    if ext in IMAGE_EXTS:
        if images.available():
            try:
                return images.thumbnail(p), "image/jpeg"
            except Exception as e:  # noqa: BLE001
                raise HttpError(415, f"Cannot read the image: {e}") from e
        if ext in WEB_IMAGE_EXTS and info["size"] <= PREVIEW_MAX:
            with open(p, "rb") as fh:
                return fh.read(), CTYPES_IMG[ext]
    if ext in TEXT_EXTS:
        with open(p, "rb") as fh:
            return fh.read(4096), "text/plain; charset=utf-8"
    raise HttpError(415, "No preview for this file type")
