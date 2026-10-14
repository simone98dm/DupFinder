"""Inventory (statistics gathered during the folder walk) and similar folders
(folders whose files are, wholly or largely, also in another folder)."""
from __future__ import annotations

import heapq
import os
from datetime import datetime

from .config import ARCHIVE_SEP, INVENTORY_DEPTH, INVENTORY_TOP

MAX_DIRS_PER_GROUP = 30      # a group spread over more folders adds little and costs pairs²
MIN_SHARE = 0.5              # folders sharing less than half of their files are not reported


class Inventory:
    """One per walker thread, merged at the end."""

    def __init__(self) -> None:
        self.files = 0
        self.bytes = 0
        self.ext: dict[str, list[int]] = {}          # extension → [files, bytes]
        self.year: dict[int, list[int]] = {}         # modification year → [files, bytes]
        self.dirs: dict[str, list[int]] = {}         # folder → [files, bytes] directly inside
        self.largest: list[tuple] = []               # min-heap (size, path, mtime)
        self.oldest: list[tuple] = []                # min-heap (-mtime, path, size)

    def add(self, dirpath: str, name: str, size: int, mtime: float) -> None:
        self.files += 1
        self.bytes += size
        ext = os.path.splitext(name)[1].lower() or "(none)"
        e = self.ext.setdefault(ext, [0, 0])
        e[0] += 1
        e[1] += size
        try:
            y = datetime.fromtimestamp(mtime).year
        except (OverflowError, OSError, ValueError):
            y = 0
        e = self.year.setdefault(y, [0, 0])
        e[0] += 1
        e[1] += size
        e = self.dirs.setdefault(dirpath, [0, 0])
        e[0] += 1
        e[1] += size
        path = os.path.join(dirpath, name)
        _push(self.largest, (size, path, mtime))
        _push(self.oldest, (-mtime, path, size))

    def merge(self, o: "Inventory") -> None:
        self.files += o.files
        self.bytes += o.bytes
        for mine, theirs in ((self.ext, o.ext), (self.year, o.year), (self.dirs, o.dirs)):
            for k, (n, b) in theirs.items():
                e = mine.setdefault(k, [0, 0])
                e[0] += n
                e[1] += b
        for it in o.largest:
            _push(self.largest, it)
        for it in o.oldest:
            _push(self.oldest, it)

    def report(self, roots: list[str]) -> dict:
        folders: dict[str, list] = {}
        for d, (n, b) in self.dirs.items():
            root = next((r for r in roots if _under(d, r)), None)
            if root is None:
                continue
            p = d
            while True:
                depth = _depth(p, root)
                if depth <= INVENTORY_DEPTH:
                    e = folders.setdefault(p, [0, 0, depth])
                    e[0] += n
                    e[1] += b
                if os.path.normcase(p) == os.path.normcase(root):
                    break
                p = os.path.dirname(p)
        return {
            "files": self.files, "bytes": self.bytes,
            "ext": sorted(([k, n, b] for k, (n, b) in self.ext.items()), key=lambda x: -x[2])[:300],
            "years": sorted([k, n, b] for k, (n, b) in self.year.items()),
            # [path, files, bytes, depth, parent] (parent "" for the roots)
            "folders": sorted(([p, n, b, dep, os.path.dirname(p) if dep else ""] for p, (n, b, dep) in folders.items()),
                              key=lambda x: -x[2])[:3000],
            "largest": [{"path": p, "size": s, "mtime": m} for s, p, m in sorted(self.largest, reverse=True)],
            "oldest": [{"path": p, "size": s, "mtime": -m} for m, p, s in sorted(self.oldest, reverse=True)],
        }


def _push(heap: list, item: tuple) -> None:
    if len(heap) < INVENTORY_TOP:
        heapq.heappush(heap, item)
    elif item > heap[0]:
        heapq.heapreplace(heap, item)


def _under(path: str, root: str) -> bool:
    a, b = os.path.normcase(path), os.path.normcase(root)
    return a == b or a.startswith(os.path.join(b, ""))


def _depth(path: str, root: str) -> int:
    rel = os.path.relpath(path, root)
    return 0 if rel == "." else rel.count(os.sep) + 1


def dir_of(path: str, chain: list[str] | None) -> str:
    """Folder of a file; for files inside archives, the folder inside the archive (archive › sub/dir)."""
    if not chain:
        return os.path.dirname(path)
    inner = chain[-1].replace("\\", "/").rpartition("/")[0]
    return ARCHIVE_SEP.join(chain[:-1] + ([inner] if inner else []))


def similar_folders(groups, index, dir_counts: dict[str, int], limit: int = 500) -> list[dict]:
    """For each pair of folders (A, B): how many files of A also have a copy in B.
    Reported when that covers at least MIN_SHARE of the files of A."""
    shared: dict[tuple[str, str], list[int]] = {}
    for g in groups:
        by_dir: dict[str, int] = {}
        for fid in g["files"]:
            info = index[fid]
            d = dir_of(info["path"], info["chain"])
            by_dir[d] = by_dir.get(d, 0) + 1
        if len(by_dir) < 2 or len(by_dir) > MAX_DIRS_PER_GROUP:
            continue
        for a, n in by_dir.items():
            for b in by_dir:
                if a != b:
                    e = shared.setdefault((a, b), [0, 0])
                    e[0] += n
                    e[1] += n * g["size"]
    out = []
    for (a, b), (n, size) in shared.items():
        total = dir_counts.get(a, 0)
        if not total or n / total < MIN_SHARE:
            continue
        out.append({"dir": a, "other": b, "shared": min(n, total), "total": total, "bytes": size,
                    "in_archive": ARCHIVE_SEP in a, "other_in_archive": ARCHIVE_SEP in b})
    out.sort(key=lambda x: (-(x["shared"] == x["total"]), -x["bytes"]))
    return out[:limit]
