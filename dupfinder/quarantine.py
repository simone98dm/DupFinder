"""Quarantine: every deletion in "quarantine" mode moves the files to
~/DupFinder_Quarantine/<date>/<original path> and writes a manifest.json there.
From here they can be listed, put back where they were, or deleted for good."""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path

from . import config
from .config import IS_WIN
from .utils import describe_os_error, is_disk_full, move_file

MANIFEST = "manifest.json"
_SESSION_RE = re.compile(r"^[\w.-]+$")


def roots() -> list[Path]:
    return list(dict.fromkeys([config.QUARANTINE_ROOT, config.LEGACY_QUARANTINE]))   # the same folder once


def stored_rel(path: str) -> str:
    """Path inside the quarantine session: C:\\Users\\a.jpg → C\\Users\\a.jpg."""
    drive, rest = os.path.splitdrive(path)
    return (drive.replace(":", "") + rest).lstrip("\\/")


def _original_from_rel(rel: str) -> str:
    """Inverse of stored_rel, for old sessions without a manifest."""
    if IS_WIN:
        first, _, rest = rel.partition(os.sep)
        if len(first) == 1 and first.isalpha():
            return f"{first}:\\{rest}"
        return "\\\\" + rel                                  # UNC path
    return "/" + rel


def record(session: Path, items: list[dict]) -> None:
    """Adds {original, stored, size, mtime} entries to the session manifest."""
    m = session / MANIFEST
    old = _load(m)
    with open(m, "w", encoding="utf-8") as fh:
        json.dump(old + items, fh, ensure_ascii=False, indent=1)


def _load(m: Path) -> list[dict]:
    try:
        with open(m, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _session(sid: str) -> Path:
    """Validates a session id ("<root index>/<folder name>"): only folders directly inside the quarantine."""
    idx, _, name = sid.partition("/")
    if not idx.isdigit() or int(idx) >= len(roots()) or not _SESSION_RE.match(name):
        raise ValueError("Unknown quarantine session.")
    d = roots()[int(idx)] / name
    if not d.is_dir():
        raise ValueError("The quarantine session no longer exists.")
    return d


def _files(d: Path) -> list[dict]:
    """The files still in a session, with their original path."""
    by_stored = {e["stored"]: e for e in _load(d / MANIFEST) if "stored" in e}
    out = []
    for dp, _, fns in os.walk(d):
        for fn in fns:
            p = os.path.join(dp, fn)
            rel = os.path.relpath(p, d)
            if rel == MANIFEST:
                continue
            e = by_stored.get(rel)
            try:
                size = os.path.getsize(p)
            except OSError:
                continue
            out.append({"stored": rel, "original": e["original"] if e else _original_from_rel(rel),
                        "size": size, "exists": os.path.exists(e["original"] if e else _original_from_rel(rel))})
    return sorted(out, key=lambda f: f["original"].lower())


def sessions() -> list[dict]:
    out = []
    for i, root in enumerate(roots()):
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir(), reverse=True):
            if not d.is_dir() or not _SESSION_RE.match(d.name):
                continue
            files = _files(d)
            if not files:
                continue
            out.append({"id": f"{i}/{d.name}", "dir": str(d), "name": d.name,
                        "files": files, "bytes": sum(f["size"] for f in files)})
    return out


def restore(sid: str, stored: list[str] | None = None) -> dict:
    """Moves the files back to their original place; an existing file there is never overwritten."""
    d = _session(sid)
    restored, errors = [], []
    for f in _files(d):
        if stored is not None and f["stored"] not in stored:
            continue
        src = str(d / f["stored"])
        if os.path.exists(f["original"]):
            errors.append({"path": f["original"], "error": "A file already exists there: not overwritten"})
            continue
        try:
            os.makedirs(os.path.dirname(f["original"]), exist_ok=True)
            move_file(src, f["original"])
            restored.append(f["original"])
        except OSError as e:
            errors.append({"path": f["original"], "error": describe_os_error(e)})
            if is_disk_full(e):
                break
    _prune(d)
    return {"restored": restored, "errors": errors}


def purge(sid: str) -> dict:
    """Deletes a whole session for good."""
    d = _session(sid)
    freed = sum(f["size"] for f in _files(d))
    errors = []

    def on_err(fn, p, exc) -> None:     # exc is the exception (onexc) or exc_info (onerror)
        errors.append({"path": p, "error": describe_os_error(exc if isinstance(exc, BaseException) else exc[1])})

    shutil.rmtree(d, **({"onexc": on_err} if sys.version_info >= (3, 12) else {"onerror": on_err}))
    return {"freed": freed if not errors else 0, "errors": errors}


def _prune(d: Path) -> None:
    """Removes the empty folders left by a restore (and the session, once empty)."""
    for dp, _, _ in sorted(os.walk(d), key=lambda t: len(t[0]), reverse=True):
        try:
            if os.listdir(dp) == [MANIFEST] and Path(dp) == d:
                os.remove(os.path.join(dp, MANIFEST))
            os.rmdir(dp)
        except OSError:
            pass
