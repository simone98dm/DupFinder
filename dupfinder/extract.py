"""Extraction of an archive found by the scan, to get rid of the duplicates it holds:
the members that already have an intact copy on disk can be skipped, and the archive
can go to quarantine / Recycle Bin once everything else is safely out.

Problems handled: not enough space (checked before starting), disk full while writing,
access denied, names already taken, member names that try to leave the folder ("zip slip"),
encrypted or damaged archives, the archive changing after the scan, cancellation."""
from __future__ import annotations

import hashlib
import os
import shutil
import time
from datetime import datetime

from . import config, quarantine
from .archives import ArchiveError, iter_members, members, safe_member_path
from .utils import Cancelled, describe_os_error, file_hash, is_disk_full


def default_dest(archive: str) -> str:
    base = os.path.basename(archive)
    stem = base.rsplit(".", 1)[0] if "." in base else base + "_files"
    return os.path.join(os.path.dirname(archive), stem)


def _free(path: str) -> int | None:
    p = os.path.abspath(path)
    while not os.path.exists(p):           # destination not created yet: its nearest existing parent
        parent = os.path.dirname(p)
        if parent == p:
            return None
        p = parent
    try:
        return shutil.disk_usage(p).free
    except OSError:
        return None


def _skippable(scanner, archive: str) -> dict[str, str]:
    """member name → expected hash, for the members whose content has an intact copy on disk."""
    out = {}
    with scanner.lock:
        for g in scanner.groups:
            infos = [scanner.index[f] for f in g["files"]]
            if not any(not i["chain"] and scanner._unchanged(i) for i in infos):
                continue
            for i in infos:
                if i["chain"] and len(i["chain"]) == 2 and i["chain"][0] == archive:
                    out[i["chain"][1]] = g["hash"]
    return out


def _check_archive(scanner, archive: str) -> None:
    if archive not in scanner.archives:
        raise ValueError("This archive is not in the scan results: scan its folder first.")
    if not os.path.isfile(archive):
        raise ValueError("The archive no longer exists: it was moved or deleted after the scan.")
    if not scanner._arc_intact({"chain": [archive]}):
        raise ValueError("The archive changed after the scan: scan again before extracting it.")


def plan(scanner, archive: str, dest: str | None = None) -> dict:
    """What an extraction would do, without touching anything."""
    _check_archive(scanner, archive)
    try:
        ms = members(archive)
    except ArchiveError as e:
        raise ValueError(str(e)) from e
    skip = _skippable(scanner, archive)
    dest = dest or default_dest(archive)
    dup = [m for m in ms if m["name"] in skip]
    enc = [m for m in ms if m["encrypted"]]
    need = sum(m["size"] for m in ms if m["name"] not in skip and not m["encrypted"])
    return {
        "archive": archive, "dest": dest, "files": len(ms), "bytes": sum(m["size"] for m in ms),
        "duplicates": len(dup), "duplicate_bytes": sum(m["size"] for m in dup),
        "encrypted": len(enc), "need": need, "need_all": sum(m["size"] for m in ms),
        "free": _free(dest), "margin": config.SPACE_MARGIN,
        "unsafe": sum(1 for m in ms if safe_member_path(dest, m["name"]) is None),
    }


def _unique(path: str) -> str:
    root, ext = os.path.splitext(path)
    n = 1
    while os.path.exists(f"{root} ({n}){ext}"):
        n += 1
    return f"{root} ({n}){ext}"


def extract_job(job, scanner, archive: str, dest: str, skip_dups: bool, after: str) -> dict:
    """after: keep | quarantine | trash — what to do with the archive once fully extracted."""
    if after not in ("keep", "quarantine", "trash"):
        raise ValueError("Invalid choice for the archive.")
    dest = os.path.abspath(os.path.expanduser((dest or default_dest(archive)).strip().strip('"')))
    p = plan(scanner, archive, dest)
    skip = _skippable(scanner, archive) if skip_dups else {}
    need = p["need"] if skip_dups else p["need_all"]
    if p["free"] is not None and p["free"] < need + config.SPACE_MARGIN:
        raise ValueError(f"Not enough space: the extraction needs {need / 2**20:,.0f} MB "
                         f"(plus {config.SPACE_MARGIN // 2**20} MB of margin), the disk has "
                         f"{p['free'] / 2**20:,.0f} MB free. Free some space or choose another folder.")
    try:
        os.makedirs(dest, exist_ok=True)
    except OSError as e:
        raise ValueError(f"Cannot create the destination folder: {describe_os_error(e)}") from e

    res = {"archive": archive, "dest": dest, "extracted": 0, "extracted_bytes": 0, "skipped": 0,
           "skipped_bytes": 0, "renamed": 0, "errors": [], "complete": False,
           "archive_action": "kept", "archive_dest": "", "stopped": ""}
    job.phase = "extract"
    job.total, job.bytes_total = p["files"], need

    def fail(name: str, msg: str) -> None:
        res["errors"].append({"path": name, "error": msg})

    try:
        for m, chunks in iter_members(archive):
            job.check()
            job.current = m["name"]
            job.done += 1
            if chunks is None:                      # encrypted zip member
                fail(m["name"], "Password protected: not extracted")
                continue
            if m["name"] in skip:
                h = hashlib.blake2b(digest_size=20)
                for b in chunks:
                    job.check()
                    h.update(b)
                if h.hexdigest() == skip[m["name"]]:
                    res["skipped"] += 1
                    res["skipped_bytes"] += m["size"]
                else:
                    fail(m["name"], "Content differs from the scan: not extracted")
                continue
            target = safe_member_path(dest, m["name"])
            if target is None:
                for _ in chunks:                    # keeps the 7-Zip stream aligned
                    pass
                fail(m["name"], "Unsafe name (it points outside the folder): not extracted")
                continue
            _write_member(job, m, chunks, target, res, fail)
        res["complete"] = not res["errors"]
    except Cancelled:
        res["stopped"] = "Cancelled: the files extracted so far stay in the folder, the archive was kept."
        job.result = res
        raise
    except ArchiveError as e:
        res["stopped"] = f"{e}: extraction stopped, the archive was kept."
    except OSError as e:
        if not is_disk_full(e):
            raise
        res["stopped"] = ("Disk full: extraction stopped, the archive was kept. "
                          "The files extracted so far stay in the folder.")

    if res["complete"] and after != "keep":
        job.phase = "archive"
        if not scanner._arc_intact({"chain": [archive]}):
            res["stopped"] = "The archive changed during the extraction: it was kept."
        else:
            stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            try:
                rel = scanner._remove(archive, after, stamp)
                if rel:
                    quarantine.record(config.QUARANTINE_ROOT / stamp,
                                      [{"original": archive, "stored": rel, "size": scanner.archives[archive][0],
                                        "mtime": scanner.archives[archive][1], "time": time.time()}])
                    res["archive_dest"] = str(config.QUARANTINE_ROOT / stamp)
                res["archive_action"] = after
            except Exception as e:  # noqa: BLE001
                res["stopped"] = f"Extraction complete, but the archive could not be removed: {describe_os_error(e)}"
    return res


def _write_member(job, m, chunks, target, res, fail) -> None:
    tmp = target + ".dupfinder-part"
    h = hashlib.blake2b(digest_size=20)
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        out = open(tmp, "wb")
    except OSError as e:
        for _ in chunks:                            # keeps the 7-Zip stream aligned
            pass
        if is_disk_full(e):
            raise
        fail(m["name"], describe_os_error(e))
        return
    try:
        with out:
            for b in chunks:
                job.check()
                h.update(b)
                out.write(b)
                job.bytes_done += len(b)
        final = target
        if os.path.exists(target):
            same = os.path.getsize(target) == m["size"] and file_hash(target) == h.hexdigest()
            if same:                                # already there with the same content
                os.remove(tmp)
                res["skipped"] += 1
                res["skipped_bytes"] += m["size"]
                return
            final = _unique(target)
            res["renamed"] += 1
        os.replace(tmp, final)
        if m["mtime"]:
            try:
                os.utime(final, (m["mtime"], m["mtime"]))
            except OSError:
                pass
        res["extracted"] += 1
        res["extracted_bytes"] += m["size"]
    except BaseException as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        if isinstance(e, OSError) and not is_disk_full(e):
            for _ in chunks:                        # the rest of this member: keeps the stream aligned
                pass
            fail(m["name"], describe_os_error(e))
            return
        raise
