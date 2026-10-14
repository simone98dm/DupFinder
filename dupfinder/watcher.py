"""Inbox watcher: checks the chosen folders every few seconds and, for each new or changed
file (once its size has stopped changing), tells whether its content is already archived
in the catalog or already on disk (files hashed by earlier scans)."""
from __future__ import annotations

import os
import threading
import time
from collections import deque

from .catalog import Catalog
from .config import WATCH_INTERVAL
from .utils import describe_os_error, file_hash

MAX_EVENTS = 500


class Watcher:
    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog
        self.folders: list[str] = []
        self.enabled = False
        self.events: deque = deque(maxlen=MAX_EVENTS)
        # id of the last event, for "new since" counts; starts from the clock so ids keep growing across restarts
        self.seq = int(time.time() * 1000)
        self._seen: dict[str, tuple] = {}             # path → (size, mtime, reported?)
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    def configure(self, folders: list[str], enabled: bool) -> None:
        folders = [os.path.abspath(os.path.expanduser(f.strip().strip('"'))) for f in folders if f.strip()]
        missing = [f for f in folders if not os.path.isdir(f)]
        if enabled and missing:
            raise ValueError(f"Folder not found: {missing[0]}")
        with self._lock:
            if folders != self.folders:
                self._seen.clear()
            self.folders, self.enabled = folders, enabled and bool(folders)
        if self.enabled and not (self._thread and self._thread.is_alive()):
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
        self._wake.set()

    def status(self, since: int = 0) -> dict:
        with self._lock:
            return {"folders": self.folders, "enabled": self.enabled, "seq": self.seq,
                    "events": [e for e in self.events if e["id"] > since][-MAX_EVENTS:]}

    def _loop(self) -> None:
        while self.enabled:
            try:
                self._poll()
            except Exception as e:  # noqa: BLE001 - the watcher must keep running
                self._event("", "error", f"Watcher error: {e}")
            self._wake.wait(WATCH_INTERVAL)
            self._wake.clear()

    def _poll(self) -> None:
        """Files already there when the watcher starts are checked too (on the second poll)."""
        current: dict[str, tuple] = {}
        for folder in list(self.folders):
            for dp, _, fns in os.walk(folder):
                for fn in fns:
                    p = os.path.join(dp, fn)
                    try:
                        st = os.stat(p)
                    except OSError:
                        continue
                    current[p] = (st.st_size, st.st_mtime)
        with self._lock:
            seen = self._seen
        new_seen = {}
        for p, (size, mtime) in current.items():
            old = seen.get(p)
            if old and old[:2] == (size, mtime):
                if not old[2] and size > 0:            # stable since the last poll: check it now
                    self._check(p, size, mtime)
                new_seen[p] = (size, mtime, True)
            else:
                new_seen[p] = (size, mtime, False)     # new or still being written
        with self._lock:
            self._seen = new_seen

    def _check(self, p: str, size: int, mtime: float) -> None:
        try:
            h = file_hash(p)
        except OSError as e:
            self._event(p, "error", describe_os_error(e))
            return
        self.catalog.save({p: {"size": size, "mtime": mtime, "full": h}})
        arch = self.catalog.archived_in(h)
        if arch:
            self._event(p, "archived", f"Already archived in {os.path.basename(arch[0]['archive'])}",
                        where=arch[0]["archive"], hash=h, size=size)
            return
        copies = self.catalog.copies_of(h, exclude=p)
        if copies:
            self._event(p, "copy", "A copy already exists on disk", where=copies[0], hash=h, size=size)
        else:
            self._event(p, "new", "Not archived; no copy among the files hashed so far", hash=h, size=size)

    def _event(self, path: str, kind: str, text: str, **extra) -> None:
        with self._lock:
            self.seq += 1
            self.events.append({"id": self.seq, "time": time.time(), "path": path, "kind": kind,
                                "text": text, **extra})
