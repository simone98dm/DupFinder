"""Similar images (resized, recompressed, sent through a chat app...): 64-bit difference
hash (dHash) and groups of images whose hashes differ by at most SIMILAR_MAX_DIST bits.
Needs Pillow (pip install Pillow); without it the feature is reported as unavailable."""
from __future__ import annotations

import io
import os
from concurrent.futures import ThreadPoolExecutor

from .catalog import Catalog
from .config import IO_WORKERS, SIMILAR_MAX_DIST
from .utils import describe_os_error

try:
    from PIL import Image, ImageOps
    Image.MAX_IMAGE_PIXELS = 200_000_000           # big panoramas are fine, absurd sizes are not
except ImportError:  # optional
    Image = None

# pigeonhole: with at most 4 differing bits, at least one of 5 chunks is identical
CHUNKS = [(0, 13), (13, 26), (26, 39), (39, 52), (52, 64)]


def available() -> bool:
    return Image is not None


def dhash(path: str) -> tuple[int, int, int]:
    """(hash, width, height). The image is reduced to 9x8 grey pixels; each bit says
    whether a pixel is brighter than its right neighbour."""
    with Image.open(path) as im:
        w, h = im.size
        im.draft("L", (64, 64))                     # JPEG: decodes at reduced size, much faster
        im = ImageOps.exif_transpose(im).convert("L").resize((9, 8), Image.Resampling.LANCZOS)
        px = im.tobytes()                           # mode L: one byte per pixel
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | (px[row * 9 + col] > px[row * 9 + col + 1])
    return bits, w, h


def thumbnail(path: str, size: int = 320) -> bytes:
    with Image.open(path) as im:
        im.draft("RGB", (size * 2, size * 2))
        im = ImageOps.exif_transpose(im)
        im.thumbnail((size, size))
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "JPEG", quality=82)
        return buf.getvalue()


def _groups(hashes: list[int]) -> list[list[int]]:
    """Indexes of the images grouped by similarity (union-find over close pairs)."""
    parent = list(range(len(hashes)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for lo, hi in CHUNKS:
        mask = (1 << (hi - lo)) - 1
        buckets: dict[int, list[int]] = {}
        for i, h in enumerate(hashes):
            buckets.setdefault((h >> lo) & mask, []).append(i)
        for idx in buckets.values():
            for a in range(len(idx)):
                for b in range(a + 1, len(idx)):
                    i, j = idx[a], idx[b]
                    if bin(hashes[i] ^ hashes[j]).count("1") <= SIMILAR_MAX_DIST:
                        ri, rj = find(i), find(j)
                        if ri != rj:
                            parent[ri] = rj
    out: dict[int, list[int]] = {}
    for i in range(len(hashes)):
        out.setdefault(find(i), []).append(i)
    return [g for g in out.values() if len(g) > 1]


def similar_job(job, scanner, cat: Catalog) -> dict:
    if not available():
        raise ValueError("Pillow is not installed: pip install Pillow")
    with scanner.lock:
        if scanner.state != "done":
            raise ValueError("Run a scan first: the images come from the scanned folders.")
        images = list(scanner.images)
        # exact duplicates (same content) already have their own view: recognized by group id
        same = {i["path"]: i["g"] for i in scanner.index.values() if not i["chain"]}
    job.phase = "hash"
    job.total = len(images)
    cache = cat.cached(p for p, _, _ in images)
    new_cache, errors = {}, []
    found: list[tuple] = []          # (path, size, mtime, hash, w, h)

    def work(item):
        p, size, mtime = item
        row = cache.get(p)
        hit = Catalog.hit(row, size, mtime, "phash")
        if hit:
            v, w, h = hit.split(":")
            return p, size, mtime, int(v, 16), int(w), int(h), False
        v, w, h = dhash(p)
        return p, size, mtime, v, w, h, True

    with ThreadPoolExecutor(max_workers=IO_WORKERS) as ex:
        futures = [ex.submit(work, it) for it in images]
        for it, fut in zip(images, futures):
            job.current = it[0]
            try:
                p, size, mtime, v, w, h, new = fut.result()
            except Exception as e:  # noqa: BLE001 - corrupt or unsupported images are only reported
                errors.append({"path": it[0], "error": describe_os_error(e) if isinstance(e, OSError) else str(e)})
                job.done += 1
                continue
            finally:
                if job.cancel.is_set():
                    for f in futures:
                        f.cancel()
            job.check()
            found.append((p, size, mtime, v, w, h))
            if new:
                new_cache[p] = {"size": size, "mtime": mtime, "phash": f"{v:016x}:{w}:{h}"}
            job.done += 1
    cat.save(new_cache)

    job.phase = "compare"
    groups, index, fid = [], {}, 0
    gid = 0
    for idxs in sorted(_groups([f[3] for f in found]), key=len, reverse=True):
        keys = [same.get(found[i][0], ("solo", i)) for i in idxs]
        if len(set(keys)) < 2:                      # only identical copies: not "similar"
            continue
        ids = []
        # best first: largest resolution, then largest file
        order = sorted(idxs, key=lambda i: (-found[i][4] * found[i][5], -found[i][1]))
        for i in order:
            p, size, mtime, v, w, h = found[i]
            key = same.get(p, ("solo", i))
            index[fid] = {"path": p, "size": size, "mtime": mtime, "g": gid, "chain": None,
                          "w": w, "h": h, "dist": bin(v ^ found[order[0]][3]).count("1"),
                          "identical": keys.count(key) > 1}
            ids.append(fid)
            fid += 1
        groups.append({"id": gid, "files": ids})
        gid += 1
    with scanner.lock:
        scanner.sim = {"groups": groups, "index": index}
    return {"images": len(images), "groups": len(groups), "errors": errors[:300], "error_count": len(errors)}


def results(scanner) -> list[dict]:
    with scanner.lock:
        idx = scanner.sim["index"]
        return [{"id": g["id"], "files": [{"id": f, **{k: idx[f][k] for k in ("path", "size", "mtime", "w", "h", "dist", "identical")}}
                                          for f in g["files"]]}
                for g in scanner.sim["groups"] if len(g["files"]) > 1]
