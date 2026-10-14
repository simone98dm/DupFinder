"""Scanner: folder walk, archive reading, duplicate search, deletion, saved session."""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import subprocess
import tempfile
import threading
import time
import zipfile
from datetime import datetime

from . import config, quarantine
from .archives import DEFLATE64, NOPASS, ArchiveError, list_7z
from .catalog import CATALOG, Catalog
from .config import (
    ARCHIVE_SEP, CACHE_VERSION, DEFAULT_EXCLUDES, IMAGE_EXTS, IO_WORKERS, IS_WIN,
    MAC_SF_DATALESS, MAX_ERRORS_KEPT, MAX_NEST, NO_WINDOW, PARTIAL, POSIX_SYSTEM_DIRS,
    READ_BUF, SEP, WIN_LINK_TAGS, WIN_PLACEHOLDER_ATTRS, WIN_REPARSE_POINT,
    WIN_SYSTEM_DIRS, ZIP_SPOOL_MEM,
)
from .inventory import Inventory, dir_of, similar_folders
from .utils import (
    SEVENZIP, Cancelled, StreamHasher, _ExactReader, _parse_7z_time, _send2trash,
    archive_kind, describe_os_error, hdd_drive_letters, is_rotational, move_file,
    normalize_roots, remove_file,
)

# archive cache file: a module attribute so the tests can redirect it
CACHE_FILE = config.CACHE_FILE
SESSION_VERSION = 1


class Scanner:
    """Runs the scan in a separate thread and keeps the results."""

    def __init__(self, catalog: Catalog | None = None) -> None:
        self.catalog = catalog or CATALOG
        self.lock = threading.Lock()
        self.cancel = threading.Event()
        self.thread: threading.Thread | None = None
        self._mlock = threading.Lock()   # counters and errors updated by the reader threads
        self._tls = threading.local()    # errors collected for the archive the thread is reading
        self.sim: dict = {"groups": [], "index": {}}   # similar images (images.py)
        self._reset()

    def _reset(self) -> None:
        self.state = "idle"            # idle | running | done | cancelled | error
        self.message = ""
        self.phase = ""                # walk | archives | partial | full
        self.roots: list[str] = []
        self.options: dict = {}
        self.files_seen = 0
        self.done = 0
        self.total = 0
        self.bytes_done = 0
        self.bytes_total = 0
        self.current = ""
        self.errors: list[dict] = []
        self.error_count = 0
        self.placeholders = 0
        self.hardlinks = 0
        self.cache_hits = 0            # files whose hash came from the catalog cache
        self.arc_scanned = 0           # archives scanned
        self.arc_cached = 0            # of which read from the cache
        self.arc_entries = 0           # files found inside archives (all levels)
        self.arc_no7z = 0              # 7z/rar archives skipped because 7-Zip is missing
        self._hdd: dict[int, bool] = {}       # st_dev → spinning disk?
        self.started = 0.0
        self.finished = 0.0
        self.groups: list[dict] = []
        self.index: dict[int, dict] = {}
        self.archives: dict[str, list] = {}   # archive on disk → [size, mtime] at scan time
        self.dir_counts: dict[str, int] = {}  # folder → files (>= min size) directly inside
        self.images: list[list] = []          # [path, size, mtime] of the images seen
        self.inventory: dict = {}
        self.folders: list[dict] = []
        self.selection: list[int] = []

    # ---------- start / status ----------
    def start(self, paths, min_size=1, excludes=None, skip_system=True, archives=True) -> None:
        roots = normalize_roots(paths)
        with self.lock:
            if self.state == "running":
                raise ValueError("A scan is already running.")
            self._reset()
            self.cancel.clear()
            self.roots = roots
            self.state = "running"
            self.started = time.time()
        self.sim = {"groups": [], "index": {}}
        excl = [e.strip().lower() for e in (excludes if excludes is not None else DEFAULT_EXCLUDES) if e.strip()]
        self.options = {"min_size": max(1, int(min_size)), "excludes": excl,
                        "skip_system": bool(skip_system), "archives": bool(archives)}
        self.thread = threading.Thread(
            target=self._run,
            args=(roots, max(1, int(min_size)), excl, bool(skip_system), bool(archives)), daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.cancel.set()

    def status(self) -> dict:
        end = self.finished or time.time()
        return {
            "state": self.state, "message": self.message, "phase": self.phase,
            "roots": self.roots, "files_seen": self.files_seen,
            "done": self.done, "total": self.total,
            "bytes_done": self.bytes_done, "bytes_total": self.bytes_total,
            "current": self.current, "error_count": self.error_count,
            "elapsed": round(end - self.started, 1) if self.started else 0,
            "session": self.started,
        }

    def results(self) -> dict:
        with self.lock:
            groups = []
            for g in self.groups:
                if len(g["files"]) < 2:
                    continue
                files = []
                for fid in g["files"]:
                    info = self.index[fid]
                    f = {"id": fid, "path": info["path"], "mtime": info["mtime"]}
                    if info["chain"]:
                        f["chain"] = info["chain"]
                    files.append(f)
                groups.append({"id": g["id"], "hash": g["hash"], "size": g["size"], "files": files})
            return {
                "groups": groups, "sep": SEP, "arc_sep": ARCHIVE_SEP, "roots": self.roots,
                "files_seen": self.files_seen, "error_count": self.error_count,
                "errors": self.errors, "placeholders": self.placeholders,
                "hardlinks": self.hardlinks, "elapsed": self.status()["elapsed"],
                "arc_scanned": self.arc_scanned, "arc_cached": self.arc_cached,
                "arc_entries": self.arc_entries, "arc_no7z": self.arc_no7z,
                "cache_hits": self.cache_hits, "session": self.started, "finished": self.finished,
                "inventory": self.inventory, "folders": self.folders,
                "images": len(self.images), "selection": self.selection,
            }

    # ---------- saved session (survives a restart, e.g. as administrator) ----------
    @staticmethod
    def _session_file():
        return config.DATA_DIR / "session.json"

    def save_session(self) -> None:
        with self.lock:
            if self.state != "done":
                return
            data = {
                "v": SESSION_VERSION, "roots": self.roots, "options": self.options,
                "started": self.started, "finished": self.finished,
                "counters": {k: getattr(self, k) for k in (
                    "files_seen", "error_count", "placeholders", "hardlinks", "cache_hits",
                    "arc_scanned", "arc_cached", "arc_entries", "arc_no7z")},
                "errors": self.errors, "groups": self.groups,
                "index": [[k, v] for k, v in self.index.items()],
                "archives": self.archives, "dir_counts": self.dir_counts, "images": self.images,
                "inventory": self.inventory, "folders": self.folders, "selection": self.selection,
            }
        _write_json(self._session_file(), data)

    def load_session(self) -> bool:
        try:
            with open(self._session_file(), encoding="utf-8") as fh:
                d = json.load(fh)
            if d.get("v") != SESSION_VERSION:
                return False
            with self.lock:
                if self.state == "running":
                    return False
                self._reset()
                for k, v in d["counters"].items():
                    setattr(self, k, v)
                self.roots, self.options = d["roots"], d["options"]
                self.started, self.finished = d["started"], d["finished"]
                self.errors, self.groups = d["errors"], d["groups"]
                self.index = {int(k): v for k, v in d["index"]}
                self.archives, self.dir_counts = d["archives"], d["dir_counts"]
                self.images, self.inventory = d["images"], d["inventory"]
                self.folders, self.selection = d["folders"], d["selection"]
                self.state = "done"
            return True
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def set_selection(self, session: float, ids) -> None:
        with self.lock:
            if session != self.started or self.state != "done":
                raise ValueError("The results changed: the selection was not saved.")
            self.selection = [int(i) for i in ids if int(i) in self.index]
        self.save_session()

    # ---------- scan ----------
    def _err(self, path: str, exc) -> None:
        msg = describe_os_error(exc) if isinstance(exc, OSError) else str(exc)
        collect = getattr(self._tls, "collect", None)
        if collect is not None:
            collect.append([path, msg])
        with self._mlock:
            self.error_count += 1
            if len(self.errors) < MAX_ERRORS_KEPT:
                self.errors.append({"path": path, "error": msg})

    def _check_cancel(self) -> None:
        if self.cancel.is_set():
            raise Cancelled()

    def _is_hdd(self, dev: int, path: str) -> bool:
        if dev not in self._hdd:
            if IS_WIN:
                self._hdd[dev] = os.path.splitdrive(path)[0][:1].upper() in hdd_drive_letters()
            else:
                self._hdd[dev] = is_rotational(path)
        return self._hdd[dev]

    def _parallel(self, jobs, fn) -> list:
        """Runs fn(path, arg) for each job (dev, path, arg) with one thread pool per
        disk: IO_WORKERS on SSDs, 1 on HDDs (parallel reads slow them down).
        Different disks work at the same time. Returns the results in job order;
        an OSError becomes the job's result, other exceptions are re-raised."""
        results: list = [None] * len(jobs)
        by_dev: dict[int, list[int]] = {}
        for i, (dev, _, _) in enumerate(jobs):
            by_dev.setdefault(dev, []).append(i)

        def worker(it) -> None:
            while not self.cancel.is_set():
                with self._mlock:
                    i = next(it, None)
                    if i is None:
                        return
                    self.done += 1
                _, path, arg = jobs[i]
                self.current = path
                try:
                    results[i] = fn(path, arg)
                except BaseException as e:  # noqa: BLE001 - reported to the main thread
                    results[i] = e

        threads = []
        for dev, idx in by_dev.items():
            n = 1 if self._is_hdd(dev, jobs[idx[0]][1]) else IO_WORKERS
            it = iter(idx)
            for _ in range(min(n, len(idx))):
                t = threading.Thread(target=worker, args=(it,), daemon=True)
                t.start()
                threads.append(t)
        for t in threads:
            t.join()
        self._check_cancel()
        for r in results:
            if isinstance(r, BaseException) and not isinstance(r, OSError):
                raise r
        return results

    def _run(self, roots, min_size, excludes, skip_system, archives) -> None:
        if IS_WIN:   # the disk query (~3 s) runs while the folders are walked
            threading.Thread(target=hdd_drive_letters, daemon=True).start()
        try:
            by_size, archive_files, inv = self._walk(roots, min_size, excludes, skip_system, archives)
            if archive_files:
                for size, chain, partial, full, mtime in self._scan_archives(archive_files, min_size):
                    by_size.setdefault(size, []).append(
                        (ARCHIVE_SEP.join(chain), mtime, (chain, partial, full)))
            final = self._find_duplicates(by_size)
            self._build_results(final)
            self.inventory = inv.report(roots)
            self.folders = similar_folders(self.groups, self.index, self.dir_counts)
            self.state = "done"
        except Cancelled:
            self.state = "cancelled"
        except Exception as e:  # noqa: BLE001
            self.state = "error"
            self.message = f"{type(e).__name__}: {e}"
        finally:
            self.finished = time.time()
            self.current = ""
        if self.state == "done":
            try:
                self.save_session()
            except OSError:
                pass        # the results stay usable, they just will not survive a restart

    def _is_excluded_dir(self, path: str, name: str, excludes, skip_system) -> bool:
        lname = name.lower()
        lpath = path.lower()
        for pat in excludes:
            if ("/" in pat or "\\" in pat):
                if fnmatch.fnmatch(lpath, pat):
                    return True
            elif fnmatch.fnmatch(lname, pat):
                return True
        if skip_system:
            if IS_WIN:
                return os.path.splitdrive(path)[1].lower() in WIN_SYSTEM_DIRS
            return path in POSIX_SYSTEM_DIRS
        return False

    @staticmethod
    def _is_win_link_dir(entry) -> bool:
        try:
            attrs = entry.stat(follow_symlinks=False).st_file_attributes
            if not attrs & WIN_REPARSE_POINT:
                return False
            return os.lstat(entry.path).st_reparse_tag in WIN_LINK_TAGS
        except (OSError, AttributeError):
            return False

    @staticmethod
    def _is_placeholder(st) -> bool:
        if IS_WIN:
            return bool(getattr(st, "st_file_attributes", 0) & WIN_PLACEHOLDER_ATTRS)
        return bool(getattr(st, "st_flags", 0) & MAC_SF_DATALESS)

    def _walk(self, roots, min_size, excludes, skip_system, archives):
        """Lists the folders with several threads (one only if every root is on an HDD).
        Each thread keeps its own results, merged at the end."""
        self.phase = "walk"
        devs = []
        for r in roots:
            try:
                devs.append(self._is_hdd(os.stat(r).st_dev, r))
            except OSError:
                devs.append(False)
        # shortcut: one decision for all roots; a mix of SSD and HDD roots is listed in parallel
        n_workers = 1 if all(devs) else IO_WORKERS
        stack = list(reversed(roots))
        pending = [len(stack)]                 # folders queued or being listed
        cv = threading.Condition()
        parts: list[tuple] = []

        def worker() -> None:
            by_size: dict[int, list] = {}
            archive_files: list[tuple[str, int, float]] = []
            inv, counts, images = Inventory(), {}, []
            parts.append((by_size, archive_files, inv, counts, images))
            while True:
                with cv:
                    while not stack and pending[0] and not self.cancel.is_set():
                        cv.wait(0.2)
                    if not stack or self.cancel.is_set():
                        return
                    d = stack.pop()
                subdirs: list[str] = []
                try:
                    self._walk_dir(d, subdirs, by_size, archive_files, inv, counts, images,
                                   min_size, excludes, skip_system, archives)
                finally:
                    with cv:
                        stack.extend(sorted(subdirs, reverse=True))
                        pending[0] += len(subdirs) - 1
                        cv.notify_all()

        threads = [threading.Thread(target=worker, daemon=True) for _ in range(n_workers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self._check_cancel()
        by_size, archive_files, inv = {}, [], Inventory()
        for bs, af, iv, counts, images in parts:
            for s, items in bs.items():
                by_size.setdefault(s, []).extend(items)
            archive_files += af
            inv.merge(iv)
            self.dir_counts.update(counts)      # folders are disjoint across threads
            self.images += images
        return by_size, archive_files, inv

    def _walk_dir(self, d, subdirs, by_size, archive_files, inv, counts, images,
                  min_size, excludes, skip_system, archives) -> None:
        self.current = d
        try:
            with os.scandir(d) as it:
                entries = list(it)
        except OSError as e:
            self._err(d, e)
            return
        seen = 0
        for e in entries:
            try:
                if e.is_symlink():
                    continue
                if e.is_dir(follow_symlinks=False):
                    if self._is_excluded_dir(e.path, e.name, excludes, skip_system):
                        continue
                    if IS_WIN and self._is_win_link_dir(e):
                        continue
                    subdirs.append(e.path)
                    continue
                if not e.is_file(follow_symlinks=False):
                    continue
                st = e.stat(follow_symlinks=False)
            except OSError as ex:
                self._err(e.path, ex)
                continue
            seen += 1
            size = st.st_size
            if self._is_placeholder(st):
                with self._mlock:
                    self.placeholders += 1
                continue
            inv.add(d, e.name, size, st.st_mtime)
            if size == 0:
                continue
            if archives and archive_kind(e.name):
                archive_files.append((e.path, size, st.st_mtime))
            if size < min_size:
                continue
            counts[d] = counts.get(d, 0) + 1
            if os.path.splitext(e.name)[1].lower() in IMAGE_EXTS:
                images.append([e.path, size, st.st_mtime])
            by_size.setdefault(size, []).append((e.path, st.st_mtime, None))
        with self._mlock:
            self.files_seen += seen

    # ---------- archives ----------
    def _scan_archives(self, archive_files, min_size) -> list[tuple]:
        """Scans every archive (using the cache if it has not changed) and returns
        the files it contains as (size, chain, partial, full, mtime)."""
        self.phase = "archives"
        self.total = len(archive_files)
        self.done = 0
        cache = self._load_cache()
        updated: dict[str, dict] = {}
        items = []
        for path, size, mtime in archive_files:
            self.archives[path] = [size, mtime]

        def add(entries) -> None:
            self.arc_scanned += 1
            self.arc_entries += len(entries)
            for c, s, p, f, m in entries:
                if s >= min_size:
                    items.append((s, c, p, f, m))
                    d = dir_of(ARCHIVE_SEP.join(c), c)
                    self.dir_counts[d] = self.dir_counts.get(d, 0) + 1

        def scan_one(path, arg):
            # runs in a reader thread: the archive's errors are collected per thread
            key, mtime = arg
            out: list = []
            self._tls.collect = []
            try:
                self._scan_archive(archive_kind(path), path, [path], 1, out, mtime)
            finally:
                errs, self._tls.collect = self._tls.collect, None
            # saved right away: if the scan is cancelled, finished archives stay in the cache
            updated[key] = {"v": CACHE_VERSION, "path": path, "errors": errs,
                            "entries": [[c[1:], s, p, f, m] for c, s, p, f, m in out]}
            return out

        jobs = []
        try:
            for path, size, mtime in archive_files:
                self._check_cancel()
                self.current = path
                key = f"{path}|{size}|{mtime}|{'7z' if SEVENZIP else 'no7z'}"
                hit = cache.get(key)
                if hit and hit.get("v") == CACHE_VERSION:
                    for epath, msg in hit.get("errors", []):
                        self._err(epath, msg)
                    self.arc_cached += 1
                    updated[key] = hit
                    add([([path] + c, s, p, f, m) for c, s, p, f, m in hit["entries"]])
                    self.done += 1
                    continue
                if archive_kind(path) != "zip" and not SEVENZIP:
                    self.arc_no7z += 1
                    self.done += 1
                    continue
                try:
                    dev = os.stat(path).st_dev
                except OSError as e:
                    self._err(path, e)
                    self.done += 1
                    continue
                jobs.append((dev, path, (key, mtime)))
            for (_, path, _), res in zip(jobs, self._parallel(jobs, scan_one)):
                if isinstance(res, OSError):
                    self._err(path, res)
                else:
                    add(res)
        finally:
            self._save_cache(cache, updated)
        return items

    @staticmethod
    def _load_cache() -> dict:
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _save_cache(old: dict, updated: dict) -> None:
        paths_updated = {v["path"] for v in updated.values()}
        merged = {k: v for k, v in old.items()
                  if isinstance(v, dict) and v.get("path") not in paths_updated and os.path.exists(v.get("path", ""))}
        merged.update(updated)
        try:
            _write_json(CACHE_FILE, merged)
        except OSError:
            pass

    def _scan_archive(self, kind, source, chain, depth, out, mtime_default) -> None:
        if kind == "zip":
            self._scan_zip(source, chain, depth, out, mtime_default)
        else:
            self._scan_7z(source, chain, depth, out, mtime_default)

    def _consume(self, chunks, name, chain, depth, out, mtime) -> None:
        """Reads an inner file in chunks, computes its hashes and, if it is itself
        an archive, scans it (up to MAX_NEST levels). Nothing is extracted to disk,
        except nested 7z/rar archives, which 7-Zip must read from a temporary file."""
        entry_chain = chain + [name]
        self.current = ARCHIVE_SEP.join(entry_chain)
        kind = archive_kind(name)
        nested = False
        if kind:
            if depth >= MAX_NEST:
                self._err(self.current, f"More than {MAX_NEST} nested archives: contents not scanned")
            elif kind != "zip" and not SEVENZIP:
                with self._mlock:
                    self.arc_no7z += 1
            else:
                nested = True
        spool = None
        if nested:
            spool = (tempfile.SpooledTemporaryFile(max_size=ZIP_SPOOL_MEM) if kind == "zip"
                     else tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(name)[1]))
        try:
            hs = StreamHasher()
            for chunk in chunks:
                self._check_cancel()
                hs.update(chunk)
                if spool is not None:
                    spool.write(chunk)
            partial, full = hs.digests()
            out.append((entry_chain, hs.size, partial, full, mtime))
            if spool is not None:
                if kind == "zip":
                    spool.seek(0)
                    self._scan_archive(kind, spool, entry_chain, depth + 1, out, mtime)
                else:
                    spool.close()
                    self._scan_archive(kind, spool.name, entry_chain, depth + 1, out, mtime)
        finally:
            if spool is not None:
                spool.close()
                if kind != "zip":
                    try:
                        os.remove(spool.name)
                    except OSError:
                        pass

    def _scan_zip(self, source, chain, depth, out, mtime_default) -> None:
        label = ARCHIVE_SEP.join(chain)
        try:
            zf = zipfile.ZipFile(source)
        except (zipfile.BadZipFile, OSError, ValueError, NotImplementedError, EOFError) as e:
            self._err(label, f"Unreadable ZIP archive: {e}")
            return
        with zf:
            # Deflate64 (zips over 2 GB made by Windows Explorer) is not in zipfile: 7-Zip reads it
            if SEVENZIP and any(i.compress_type == DEFLATE64 for i in zf.infolist()):
                self._zip_via_7z(source, chain, depth, out, mtime_default)
                return
            for info in zf.infolist():
                self._check_cancel()
                if info.is_dir() or info.file_size == 0:
                    continue
                name = info.filename
                if info.flag_bits & 0x1:
                    self._err(f"{label}{ARCHIVE_SEP}{name}", "Password protected: not scanned")
                    continue
                try:
                    mt = time.mktime(info.date_time + (0, 0, -1))
                except (OverflowError, ValueError):
                    mt = mtime_default
                try:
                    with zf.open(info) as fh:
                        self._consume(iter(lambda: fh.read(READ_BUF), b""), name, chain, depth, out, mt)
                except Cancelled:
                    raise
                except NotImplementedError:
                    self._err(f"{label}{ARCHIVE_SEP}{name}", "Unsupported compression method")
                except Exception as e:  # noqa: BLE001
                    self._err(f"{label}{ARCHIVE_SEP}{name}", f"Read error: {e}")

    def _zip_via_7z(self, source, chain, depth, out, mtime_default) -> None:
        if isinstance(source, str):
            self._scan_7z(source, chain, depth, out, mtime_default)
            return
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")   # nested zip: 7-Zip needs a file
        try:
            source.seek(0)
            for b in iter(lambda: source.read(READ_BUF), b""):
                tmp.write(b)
            tmp.close()
            self._scan_7z(tmp.name, chain, depth, out, mtime_default)
        finally:
            tmp.close()
            try:
                os.remove(tmp.name)
            except OSError:
                pass

    def _scan_7z(self, source, chain, depth, out, mtime_default) -> None:
        """7z and RAR through 7-Zip: a file listing, then a single extraction pass
        to stdout (files arrive one after another in listing order). This way even
        "solid" archives are decompressed only once."""
        label = ARCHIVE_SEP.join(chain)
        try:
            files = list_7z(source)
        except ArchiveError as e:
            self._err(label, f"{e}: not scanned")
            return

        local: list = []
        ok = True
        proc = subprocess.Popen([SEVENZIP, "x", "-so", "-bd", NOPASS, source],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
        try:
            for e in files:
                try:
                    size = int(e.get("Size") or 0)
                except ValueError:
                    ok = False
                    break
                if size == 0:
                    continue
                reader = _ExactReader(proc.stdout, size)
                try:
                    self._consume(reader, e.get("Path", "?"), chain, depth, local,
                                  _parse_7z_time(e.get("Modified")) or mtime_default)
                except Cancelled:
                    raise
                except Exception:  # noqa: BLE001
                    ok = False
                    break
                if reader.short:
                    ok = False
                    break
            if ok and proc.stdout.read(1):
                ok = False                       # more data than expected: listing and stream do not match
            ok = ok and proc.wait() == 0
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            proc.stdout.close()
        if ok:
            out.extend(local)
        else:
            self._err(label, "Archive damaged or not fully readable: contents ignored")

    # ---------- comparison ----------
    @staticmethod
    def _partial_hash(path: str, size: int) -> str:
        h = hashlib.blake2b(digest_size=20)
        with open(path, "rb") as f:
            if size <= 2 * PARTIAL:
                h.update(f.read())          # small file: this is already the full hash
            else:
                h.update(f.read(PARTIAL))
                f.seek(-PARTIAL, os.SEEK_END)
                h.update(f.read(PARTIAL))
        return h.hexdigest()

    def _full_hash(self, path: str) -> str:
        h = hashlib.blake2b(digest_size=20)
        buf = bytearray(READ_BUF)
        mv = memoryview(buf)
        with open(path, "rb", buffering=0) as f:
            while True:
                self._check_cancel()
                n = f.readinto(buf)
                if not n:
                    break
                h.update(mv[:n])
                with self._mlock:
                    self.bytes_done += n
        return h.hexdigest()

    def _find_duplicates(self, by_size) -> list[tuple[int, str, list]]:
        # Each item is (path, mtime, arc): arc is None for files on disk,
        # or (chain, quick hash, full hash) for files inside archives.
        # Hashes of unchanged files (same size and mtime) come from the catalog cache.
        # 1) only sizes with at least two files
        buckets = [(s, items) for s, items in by_size.items() if len(items) > 1]
        by_size.clear()
        cache = self.catalog.cached(it[0] for _, items in buckets for it in items if it[2] is None)
        new_cache: dict[str, dict] = {}

        # 2) quick hash (head + tail), skipping hardlinks to the same physical file
        self.phase = "partial"
        self.total = sum(len(items) for _, items in buckets)
        self.done = 0
        subs: list[dict[str, list]] = []   # per size: quick hash → items
        devs: dict[str, int] = {}          # path → disk, for step 3
        jobs, owners = [], []
        try:
            for size, items in buckets:
                seen = set()
                sub: dict[str, list] = {}
                subs.append(sub)
                for item in items:
                    self._check_cancel()
                    path, mtime, arc = item
                    if arc is not None:
                        self.done += 1
                        sub.setdefault(arc[1], []).append(item)
                        continue
                    try:
                        st = os.stat(path)
                    except OSError as e:
                        self.done += 1
                        self._err(path, e)
                        continue
                    key = (st.st_dev, st.st_ino)
                    if st.st_ino and key in seen:
                        self.done += 1
                        self.hardlinks += 1
                        continue
                    seen.add(key)
                    devs[path] = st.st_dev
                    ph = Catalog.hit(cache.get(path), size, mtime, "partial")
                    if ph:
                        self.done += 1
                        self.cache_hits += 1
                        sub.setdefault(ph, []).append(item)
                        continue
                    jobs.append((st.st_dev, path, size))
                    owners.append((sub, item))
            for (sub, item), (_, path, size), ph in zip(owners, jobs, self._parallel(jobs, self._partial_hash)):
                if isinstance(ph, OSError):
                    self._err(path, ph)
                else:
                    sub.setdefault(ph, []).append(item)
                    new_cache[path] = {"size": size, "mtime": item[1], "partial": ph}
            candidates = [(size, ph, lst) for (size, _), sub in zip(buckets, subs)
                          for ph, lst in sub.items() if len(lst) > 1]

            # 3) full hash only where needed (files in archives and cached files already have it)
            self.phase = "full"
            final, big = [], []
            jobs, owners = [], []
            for size, ph, lst in candidates:
                if size <= 2 * PARTIAL:
                    final.append((size, ph, lst))
                    continue
                sub = {}
                big.append((size, sub))
                for item in lst:
                    path, mtime, arc = item
                    if arc is not None:
                        sub.setdefault(arc[2], []).append(item)
                        continue
                    fh = Catalog.hit(cache.get(path), size, mtime, "full")
                    if fh:
                        sub.setdefault(fh, []).append(item)
                    else:
                        jobs.append((devs[path], path, size))
                        owners.append((sub, item))
            self.bytes_total = sum(s for _, _, s in jobs)
            self.bytes_done = 0
            self.done, self.total = 0, len(jobs)
            for (sub, item), (_, path, size), fh in zip(owners, jobs,
                                                         self._parallel(jobs, lambda p, _: self._full_hash(p))):
                if isinstance(fh, OSError):
                    self._err(path, fh)
                else:
                    sub.setdefault(fh, []).append(item)
                    new_cache.setdefault(path, {"size": size, "mtime": item[1]})["full"] = fh
            final.extend((size, fh, l) for size, sub in big for fh, l in sub.items() if len(l) > 1)
        finally:
            try:
                self.catalog.save(new_cache)       # also when cancelled: the work done is kept
            except Exception:  # noqa: BLE001 - a broken cache must not break the scan
                pass
        return final

    def _build_results(self, final) -> None:
        def weight(t):
            size, _, lst = t
            loose = sum(1 for it in lst if it[2] is None)
            return (size * max(loose - 1, 0), size * (len(lst) - 1))

        final.sort(key=weight, reverse=True)
        groups, index, fid = [], {}, 0
        for gid, (size, h, lst) in enumerate(final):
            ids = []
            for path, mtime, arc in sorted(lst, key=lambda it: (it[2] is not None, it[0])):
                index[fid] = {"path": path, "size": size, "mtime": mtime, "g": gid,
                              "chain": arc[0] if arc else None}
                ids.append(fid)
                fid += 1
            groups.append({"id": gid, "hash": h, "size": size, "files": ids})
        with self.lock:
            self.groups, self.index = groups, index

    # ---------- deletion ----------
    @staticmethod
    def _unchanged(info: dict) -> bool:
        if info["chain"]:
            return False
        try:
            st = os.stat(info["path"])
        except OSError:
            return False
        return st.st_size == info["size"] and abs(st.st_mtime - info["mtime"]) < 2

    def _arc_intact(self, info: dict) -> bool:
        """A copy inside an archive counts as kept only if the archive on disk is still
        exactly the one that was scanned (same size and modification time)."""
        if not info["chain"]:
            return False
        outer = info["chain"][0]
        seen = self.archives.get(outer)
        try:
            st = os.stat(outer)
        except OSError:
            return False
        return bool(seen) and st.st_size == seen[0] and abs(st.st_mtime - seen[1]) < 2

    def delete(self, ids, mode: str, arc_keep: bool = False, similar: bool = False) -> dict:
        """Deletes files of the duplicate groups (or of the similar-image groups).
        Every group keeps at least one intact copy on disk; with arc_keep a copy inside
        an unchanged archive is enough (duplicate groups only)."""
        if mode not in ("trash", "quarantine", "permanent"):
            raise ValueError("Invalid deletion mode.")
        if mode == "trash" and _send2trash is None:
            raise ValueError("The Recycle Bin is not available: install send2trash (pip install send2trash).")
        with self.lock:
            if self.state != "done":
                raise ValueError("No scan results available.")
            src = self.sim if similar else {"groups": self.groups, "index": self.index}
            index = src["index"]
            groups = {g["id"]: g for g in src["groups"]}
            wanted = {int(i) for i in ids}
            stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            deleted, errors, freed, moved = [], [], 0, []

            for fid in wanted - index.keys():
                errors.append({"id": fid, "path": "?", "reason": "Unknown file"})

            by_group: dict[int, list[int]] = {}
            for fid in wanted & index.keys():
                if index[fid]["chain"]:
                    errors.append({"id": fid, "path": index[fid]["path"],
                                   "reason": "Inside an archive: cannot be deleted"})
                    continue
                by_group.setdefault(index[fid]["g"], []).append(fid)

            for gid, sel in by_group.items():
                group = groups[gid]
                # at least one copy must remain, existing and identical to the scanned one
                keepers = [f for f in group["files"] if f not in wanted and (
                    self._unchanged(index[f]) or (arc_keep and not similar and self._arc_intact(index[f])))]
                if not keepers:
                    why = ("no intact copy would remain on disk or in an unchanged archive" if arc_keep
                           else "no intact copy would remain outside archives")
                    for fid in sel:
                        errors.append({"id": fid, "path": index[fid]["path"], "reason": "Skipped: " + why})
                    continue
                for fid in sel:
                    info = index[fid]
                    path = info["path"]
                    if not self._unchanged(info):
                        errors.append({"id": fid, "path": path,
                                       "reason": "Skipped: the file was modified or moved after the scan"})
                        continue
                    try:
                        dest = self._remove(path, mode, stamp)
                    except Exception as e:  # noqa: BLE001
                        errors.append({"id": fid, "path": path, "reason": describe_os_error(e)})
                        continue
                    if dest:
                        moved.append({"original": path, "stored": dest, "size": info["size"],
                                      "mtime": info["mtime"], "time": time.time()})
                    deleted.append(fid)
                    freed += info["size"]
                group["files"] = [f for f in group["files"] if f not in deleted]

            for fid in deleted:
                index.pop(fid, None)
            if not similar:
                self.selection = [i for i in self.selection if i not in deleted]
            if moved:
                try:
                    quarantine.record(config.QUARANTINE_ROOT / stamp, moved)
                except OSError:
                    pass       # the derived original paths still allow a restore

        if deleted and not similar:
            try:
                self.save_session()
            except OSError:
                pass
        return {
            "deleted": deleted, "errors": errors, "freed": freed, "mode": mode,
            "quarantine_dir": str(config.QUARANTINE_ROOT / stamp) if mode == "quarantine" and deleted else "",
        }

    @staticmethod
    def _remove(path: str, mode: str, stamp: str) -> str:
        """Deletes one file; in quarantine mode returns its path inside the session."""
        if mode == "trash":
            _send2trash(path)
        elif mode == "quarantine":
            rel = quarantine.stored_rel(path)
            dest = config.QUARANTINE_ROOT / stamp / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            move_file(path, str(dest))
            return rel
        else:
            remove_file(path)
        return ""


def _write_json(path, data) -> None:
    """Atomic write: a crash halfway never leaves a broken file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    os.replace(tmp, path)
