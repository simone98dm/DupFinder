"""SQLite catalog (~/.dupfinder/catalog.db):
- hashes: hash cache of files on disk, valid while size and mtime do not change (fast rescans);
- archives / entries: the zips created by DupFinder and the files they hold, with the original
  path, for search, restore and integrity checks. External disks are found by volume serial."""
from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import threading
import time
import zipfile
from datetime import datetime

from . import config
from .config import COMPRESSED_EXTS, DEFAULT_EXCLUDES, READ_BUF
from .utils import (describe_os_error, file_hash, find_on_volume, is_disk_full,
                    normalize_roots, volume_info)

SCHEMA = """
CREATE TABLE IF NOT EXISTS hashes(path TEXT PRIMARY KEY, size INTEGER, mtime REAL,
                                  partial TEXT, full TEXT, phash TEXT);
CREATE INDEX IF NOT EXISTS hashes_full ON hashes(full);
CREATE TABLE IF NOT EXISTS archives(id INTEGER PRIMARY KEY, path TEXT, created REAL, files INTEGER,
                                    bytes INTEGER, vol_serial TEXT, vol_label TEXT, vol_rel TEXT,
                                    verified REAL, verify_status TEXT);
CREATE TABLE IF NOT EXISTS entries(id INTEGER PRIMARY KEY, archive_id INTEGER, member TEXT,
                                   original TEXT, hash TEXT, size INTEGER, mtime REAL);
CREATE INDEX IF NOT EXISTS entries_hash ON entries(hash);
CREATE INDEX IF NOT EXISTS entries_orig ON entries(original);
"""
BATCH = 500          # SQLite parameters per IN (...) query


def _chunks(seq, n=BATCH):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


class Catalog:
    def __init__(self, path: str | None = None) -> None:
        self.path = path
        self.lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None

    def db(self) -> sqlite3.Connection:
        if self._conn is None:
            p = self.path or str(config.DATA_DIR / "catalog.db")
            os.makedirs(os.path.dirname(p), exist_ok=True)
            c = sqlite3.connect(p, check_same_thread=False)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript(SCHEMA)
            self._conn = c
        return self._conn

    def close(self) -> None:
        with self.lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    # ---------- hash cache ----------
    def cached(self, paths) -> dict[str, dict]:
        """path → {size, mtime, partial, full, phash} for the paths already in the cache."""
        out = {}
        with self.lock:
            for part in _chunks(paths):
                q = f"SELECT * FROM hashes WHERE path IN ({','.join('?' * len(part))})"
                for r in self.db().execute(q, part):
                    out[r["path"]] = dict(r)
        return out

    @staticmethod
    def hit(row: dict | None, size: int, mtime: float, field: str):
        """The cached value of field, if the file has not changed since it was stored."""
        if row and row["size"] == size and row["mtime"] == mtime:
            return row[field]
        return None

    def save(self, rows: dict[str, dict]) -> None:
        """rows: path → {size, mtime, and any of partial/full/phash}. Values already stored
        for the same size and mtime are kept; a changed file starts from scratch."""
        if not rows:
            return
        with self.lock:
            old = self.cached(rows.keys())
            data = []
            for path, r in rows.items():
                o = old.get(path)
                same = o and o["size"] == r["size"] and o["mtime"] == r["mtime"]
                vals = {f: r.get(f) or (o[f] if same else None) for f in ("partial", "full", "phash")}
                data.append((path, r["size"], r["mtime"], vals["partial"], vals["full"], vals["phash"]))
            with self.db():
                self.db().executemany("INSERT OR REPLACE INTO hashes VALUES (?,?,?,?,?,?)", data)

    def copies_of(self, full: str, exclude: str = "") -> list[str]:
        """Files on disk last seen with this content (they may have changed since)."""
        with self.lock:
            rows = self.db().execute("SELECT path, size, mtime FROM hashes WHERE full = ? AND path != ?",
                                     (full, exclude)).fetchall()
        out = []
        for r in rows:
            try:
                st = os.stat(r["path"])
            except OSError:
                continue
            if st.st_size == r["size"] and st.st_mtime == r["mtime"]:
                out.append(r["path"])
        return out

    # ---------- archives ----------
    def known_hashes(self, hashes) -> set[str]:
        out = set()
        with self.lock:
            for part in _chunks(hashes):
                q = f"SELECT DISTINCT hash FROM entries WHERE hash IN ({','.join('?' * len(part))})"
                out.update(r[0] for r in self.db().execute(q, part))
        return out

    def resolve(self, a) -> str | None:
        """Current path of a catalog archive: where it was, or on the same disk under another letter."""
        if os.path.exists(a["path"]):
            return a["path"]
        return find_on_volume(a["vol_serial"], a["vol_rel"])

    def archives(self) -> list[dict]:
        with self.lock:
            rows = [dict(r) for r in self.db().execute("SELECT * FROM archives ORDER BY created DESC")]
        for a in rows:
            a["current"] = self.resolve(a)
        return rows

    def summary(self) -> dict:
        archives = self.archives()
        return {"archives": archives, "files": sum(a["files"] for a in archives),
                "bytes": sum(a["bytes"] for a in archives)}

    def archived_in(self, full: str) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.db().execute(
                "SELECT e.member, e.original, a.path AS archive FROM entries e "
                "JOIN archives a ON a.id = e.archive_id WHERE e.hash = ?", (full,))]

    def search(self, q: str, limit: int = 500) -> list[dict]:
        q = q.strip()
        if not q:
            return []
        with self.lock:
            if len(q) == 40 and all(c in "0123456789abcdef" for c in q.lower()):
                where, arg = "e.hash = ?", q.lower()
            else:
                where, arg = "e.original LIKE ? ESCAPE '\\'", "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            rows = [dict(r) for r in self.db().execute(
                "SELECT e.id, e.member, e.original, e.hash, e.size, e.mtime, e.archive_id, a.path AS archive, "
                f"a.created FROM entries e JOIN archives a ON a.id = e.archive_id WHERE {where} "
                "ORDER BY e.original LIMIT ?", (arg, limit))]
        return rows

    def forget(self, archive_id: int) -> None:
        """Removes an archive from the catalog (the zip file is not touched)."""
        with self.lock, self.db():
            self.db().execute("DELETE FROM entries WHERE archive_id = ?", (archive_id,))
            self.db().execute("DELETE FROM archives WHERE id = ?", (archive_id,))


def member_name(path: str) -> str:
    """Original path → name inside the zip: C:\\Users\\a.jpg → C/Users/a.jpg, /home/a.jpg → home/a.jpg."""
    drive, rest = os.path.splitdrive(os.path.abspath(path))
    if drive.startswith(("\\\\", "//")):
        drive = "UNC/" + drive.lstrip("\\/")
    parts = [p for p in (drive.replace(":", "") + "/" + rest.replace("\\", "/")).split("/") if p]
    return "/".join(parts)


def _under(path: str, folder: str) -> bool:
    return os.path.normcase(os.path.join(path, "")).startswith(os.path.normcase(os.path.join(folder, "")))


def _hash_member(zf: zipfile.ZipFile, name: str, job) -> str:
    h = hashlib.blake2b(digest_size=20)
    with zf.open(name) as fh:
        for b in iter(lambda: fh.read(READ_BUF), b""):
            job.check()
            h.update(b)
            job.bytes_done += len(b)
    return h.hexdigest()


# ---------- jobs (run by jobs.start) ----------
def archive_job(job, cat: Catalog, sources: list[str], dest: str) -> dict:
    """Puts in a new zip the files of sources that are not in the catalog yet, checks the zip
    by reading it back, then records it. The original files are never touched."""
    sources = normalize_roots(sources)
    dest = os.path.abspath(os.path.expanduser(dest.strip().strip('"')))
    if not dest:
        raise ValueError("Choose the folder where the archives go.")
    os.makedirs(dest, exist_ok=True)
    excl = {e.lower() for e in DEFAULT_EXCLUDES}

    job.phase = "walk"
    files, errors = [], []
    for root in sources:
        for dp, dns, fns in os.walk(root, onerror=lambda e: errors.append({"path": e.filename, "error": describe_os_error(e)})):
            job.check()
            job.current = dp
            dns[:] = [d for d in dns if d.lower() not in excl and not os.path.islink(os.path.join(dp, d))
                      and not _under(os.path.join(dp, d), dest)]
            for fn in fns:
                p = os.path.join(dp, fn)
                try:
                    st = os.stat(p, follow_symlinks=False)
                except OSError as e:
                    errors.append({"path": p, "error": describe_os_error(e)})
                    continue
                if os.path.islink(p) or st.st_size == 0:
                    continue
                files.append((p, st.st_size, st.st_mtime))

    job.phase = "hash"
    job.total, job.done = len(files), 0
    job.bytes_total = sum(s for _, s, _ in files)
    cache = cat.cached(p for p, _, _ in files)
    new_cache, hashed = {}, []
    for p, size, mtime in files:
        job.check()
        job.current = p
        h = Catalog.hit(cache.get(p), size, mtime, "full")
        if not h:
            try:
                h = file_hash(p, job.check)
            except OSError as e:
                errors.append({"path": p, "error": describe_os_error(e)})
                job.done += 1
                continue
            new_cache[p] = {"size": size, "mtime": mtime, "full": h}
        hashed.append((p, size, mtime, h))
        job.done += 1
        job.bytes_done += size
    cat.save(new_cache)

    known = cat.known_hashes(h for *_, h in hashed)
    todo, seen = [], set()
    for item in hashed:
        if item[3] in known or item[3] in seen:
            continue
        seen.add(item[3])
        todo.append(item)
    result = {"archive": "", "files": 0, "bytes": 0, "already": len(hashed) - len(todo), "errors": errors}
    if not todo:
        return result

    need = sum(s for _, s, _, _ in todo)
    free = _free_space(dest)
    if free is not None and free < need + config.SPACE_MARGIN:
        raise ValueError(f"Not enough space in {dest}: {need / 2**20:.0f} MB needed at most, "
                         f"{free / 2**20:.0f} MB free.")

    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    final = os.path.join(dest, f"DupFinder_{stamp}.zip")
    tmp = final + ".part"
    job.phase = "write"
    job.total, job.done, job.bytes_total, job.bytes_done = len(todo), 0, need, 0
    written, names = [], set()
    try:
        with zipfile.ZipFile(tmp, "w", allowZip64=True, strict_timestamps=False) as zf:
            for p, size, mtime, h in todo:
                job.check()
                job.current = p
                name = member_name(p)
                while name in names:                       # same path on two roots: cannot happen, but be safe
                    name += "_"
                names.add(name)
                ext = os.path.splitext(p)[1].lower()
                try:
                    zf.write(p, name, zipfile.ZIP_STORED if ext in COMPRESSED_EXTS else zipfile.ZIP_DEFLATED)
                except OSError as e:
                    if is_disk_full(e):
                        raise
                    errors.append({"path": p, "error": describe_os_error(e)})
                    continue
                written.append((name, p, size, mtime))
                job.done += 1
                job.bytes_done += size

        # read everything back: the catalog records the content that is really in the zip
        job.phase = "verify"
        job.done, job.bytes_done = 0, 0
        rows = []
        with zipfile.ZipFile(tmp) as zf:
            for name, p, size, mtime in written:
                job.current = p
                rows.append((name, p, _hash_member(zf, name, job), size, mtime))
                job.done += 1
        os.replace(tmp, final)
    except BaseException as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        if is_disk_full(e):
            raise ValueError(f"Disk full while writing {final}: nothing was archived. "
                             "Free some space or choose another folder.") from e
        raise

    serial, label, rel = volume_info(final)
    with cat.lock, cat.db():
        cur = cat.db().execute(
            "INSERT INTO archives(path, created, files, bytes, vol_serial, vol_label, vol_rel, verified, verify_status) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (final, time.time(), len(rows), sum(r[3] for r in rows), serial, label, rel, time.time(), "ok"))
        cat.db().executemany("INSERT INTO entries(archive_id, member, original, hash, size, mtime) VALUES (?,?,?,?,?,?)",
                             [(cur.lastrowid, *r) for r in rows])
    result.update(archive=final, files=len(rows), bytes=sum(r[3] for r in rows))
    return result


def _free_space(path: str) -> int | None:
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return None


def verify_job(job, cat: Catalog, ids: list[int] | None = None) -> list[dict]:
    """Reads every catalog archive and checks the content of each file against its hash."""
    archives = [a for a in cat.archives() if not ids or a["id"] in ids]
    job.total = len(archives)
    out = []
    for a in archives:
        job.check()
        job.current = a["path"]
        path, bad, missing = a["current"], 0, 0
        if not path:
            status = "missing"
        else:
            with cat.lock:
                entries = cat.db().execute("SELECT member, hash FROM entries WHERE archive_id = ?", (a["id"],)).fetchall()
            try:
                with zipfile.ZipFile(path) as zf:
                    names = set(zf.namelist())
                    for e in entries:
                        if e["member"] not in names:
                            missing += 1
                        elif _hash_member(zf, e["member"], job) != e["hash"]:
                            bad += 1
                status = "ok" if not bad and not missing else "damaged"
            except (zipfile.BadZipFile, OSError, EOFError, ValueError) as e:
                status, bad = "damaged", len(entries)
                job.message = str(e)
        with cat.lock, cat.db():
            cat.db().execute("UPDATE archives SET verified = ?, verify_status = ? WHERE id = ?",
                             (time.time(), status, a["id"]))
        out.append({"id": a["id"], "path": path or a["path"], "status": status, "bad": bad, "missing": missing})
        job.done += 1
    return out


def restore_job(job, cat: Catalog, ids: list[int], target: str | None) -> dict:
    """Extracts catalog entries to their original path (target None) or under target,
    checking the hash; existing files are never overwritten."""
    with cat.lock:
        rows = []
        for part in _chunks(ids):
            rows += [dict(r) for r in cat.db().execute(
                f"SELECT e.*, a.path AS apath, a.vol_serial, a.vol_rel FROM entries e "
                f"JOIN archives a ON a.id = e.archive_id WHERE e.id IN ({','.join('?' * len(part))})", part)]
    job.total = len(rows)
    job.bytes_total = sum(r["size"] for r in rows)
    restored, errors = [], []
    by_archive: dict[int, list[dict]] = {}
    for r in rows:
        by_archive.setdefault(r["archive_id"], []).append(r)
    for rs in by_archive.values():
        a = {"path": rs[0]["apath"], "vol_serial": rs[0]["vol_serial"], "vol_rel": rs[0]["vol_rel"]}
        path = cat.resolve(a)
        if not path:
            errors += [{"path": r["original"], "error": f"Archive not found: {a['path']} (is the disk connected?)"} for r in rs]
            job.done += len(rs)
            continue
        try:
            zf = zipfile.ZipFile(path)
        except (zipfile.BadZipFile, OSError) as e:
            errors += [{"path": r["original"], "error": f"Archive unreadable: {e}"} for r in rs]
            job.done += len(rs)
            continue
        with zf:
            for r in rs:
                job.check()
                dest = r["original"] if not target else os.path.join(target, *r["member"].split("/"))
                job.current = dest
                try:
                    _restore_one(zf, r, dest, job)
                    restored.append(dest)
                except FileExistsError:
                    errors.append({"path": dest, "error": "A file already exists there: not overwritten"})
                except ValueError as e:
                    errors.append({"path": dest, "error": str(e)})
                except OSError as e:
                    errors.append({"path": dest, "error": describe_os_error(e)})
                    if is_disk_full(e):
                        raise ValueError("Disk full: restore stopped. " + f"{len(restored)} files restored.") from e
                job.done += 1
    return {"restored": restored, "errors": errors}


def _restore_one(zf: zipfile.ZipFile, r: dict, dest: str, job) -> None:
    if os.path.exists(dest):
        raise FileExistsError(dest)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".dupfinder-part"
    h = hashlib.blake2b(digest_size=20)
    try:
        with zf.open(r["member"]) as src, open(tmp, "wb") as out:
            for b in iter(lambda: src.read(READ_BUF), b""):
                job.check()
                h.update(b)
                out.write(b)
                job.bytes_done += len(b)
        if h.hexdigest() != r["hash"]:
            raise ValueError("The content in the archive does not match the catalog: not restored")
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    if r["mtime"]:
        os.utime(dest, (r["mtime"], r["mtime"]))


CATALOG = Catalog()
