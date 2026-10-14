"""Reading archive members as streams: ZIP with zipfile, 7z and RAR through the 7-Zip command line.
Used by the scanner (hashes) and by the extraction (writing the members to disk)."""
from __future__ import annotations

import os
import subprocess
import time
import zipfile

from .config import NO_WINDOW, READ_BUF
from .utils import SEVENZIP, _ExactReader, _parse_7z_time, archive_kind

NOPASS = "-p_dupfinder_nopassword_"    # keeps 7-Zip from waiting for a password
DEFLATE64 = 9


class ArchiveError(Exception):
    """The archive as a whole cannot be read (damaged, encrypted, unsupported)."""


def list_7z(source: str) -> list[dict]:
    """7-Zip technical listing (-slt): one dict per file, folders excluded, in stream order."""
    try:
        r = subprocess.run([SEVENZIP, "l", "-slt", "-ba", "-sccUTF-8", NOPASS, source],
                           stdin=subprocess.DEVNULL, capture_output=True,
                           timeout=900, creationflags=NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ArchiveError(f"7-Zip could not read the archive: {e}") from e
    if r.returncode != 0:
        msg = (r.stdout + r.stderr).decode("utf-8", "replace").lower()
        if "password" in msg or "encrypted" in msg:
            raise ArchiveError("Password-protected archive")
        raise ArchiveError("Archive damaged or in an unsupported format")
    entries, cur = [], {}
    for line in r.stdout.decode("utf-8", "replace").splitlines() + [""]:
        if not line.strip():
            if cur:
                entries.append(cur)
                cur = {}
            continue
        k, _, v = line.partition(" = ")
        cur[k.strip()] = v
    files = [e for e in entries
             if e.get("Folder") != "+" and "D" not in e.get("Attributes", "").split(" ")[0]]
    if any(e.get("Encrypted") == "+" for e in files):
        raise ArchiveError("Password-protected archive")
    return files


def members(path: str) -> list[dict]:
    """Files in a top-level archive: name, size, mtime, encrypted. Raises ArchiveError."""
    if archive_kind(path) == "zip":
        try:
            with zipfile.ZipFile(path) as zf:
                return [{"name": i.filename, "size": i.file_size, "encrypted": bool(i.flag_bits & 1),
                         "mtime": _zip_time(i)} for i in zf.infolist() if not i.is_dir()]
        except (zipfile.BadZipFile, OSError, ValueError, EOFError) as e:
            raise ArchiveError(f"Unreadable ZIP archive: {e}") from e
    if not SEVENZIP:
        raise ArchiveError("7-Zip is not installed: 7z and RAR archives cannot be read")
    return [{"name": e.get("Path", "?"), "size": int(e.get("Size") or 0), "encrypted": False,
             "mtime": _parse_7z_time(e.get("Modified"))} for e in list_7z(path)]


def _zip_time(info) -> float | None:
    try:
        return time.mktime(info.date_time + (0, 0, -1))
    except (OverflowError, ValueError):
        return None


def iter_members(path: str):
    """Yields (member dict, chunk iterator) for every file of a top-level archive, in order.
    The iterator must be consumed before asking for the next member (encrypted zip members
    come with None). Raises ArchiveError when the archive cannot be read."""
    use_zip = archive_kind(path) == "zip"
    if use_zip:
        try:
            zf = zipfile.ZipFile(path)
        except (zipfile.BadZipFile, OSError, ValueError, EOFError) as e:
            raise ArchiveError(f"Unreadable ZIP archive: {e}") from e
        # Deflate64 (big zips made by Windows Explorer) is not in zipfile: 7-Zip reads it
        if SEVENZIP and any(i.compress_type == DEFLATE64 for i in zf.infolist()):
            zf.close()
            use_zip = False
    if use_zip:
        with zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                m = {"name": info.filename, "size": info.file_size,
                     "encrypted": bool(info.flag_bits & 1), "mtime": _zip_time(info)}
                if m["encrypted"]:
                    yield m, None
                    continue
                try:
                    fh = zf.open(info)
                except NotImplementedError as e:
                    raise ArchiveError(f"{info.filename}: unsupported compression method") from e
                with fh:
                    yield m, iter(lambda: fh.read(READ_BUF), b"")
        return
    if not SEVENZIP:
        raise ArchiveError("7-Zip is not installed: 7z and RAR archives cannot be read")
    files = list_7z(path)
    proc = subprocess.Popen([SEVENZIP, "x", "-so", "-bd", NOPASS, path],
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
    try:
        for e in files:
            size = int(e.get("Size") or 0)
            m = {"name": e.get("Path", "?"), "size": size, "encrypted": False,
                 "mtime": _parse_7z_time(e.get("Modified"))}
            if size == 0:
                yield m, iter(())
                continue
            reader = _ExactReader(proc.stdout, size)
            yield m, reader
            if reader.short:
                raise ArchiveError("Archive damaged or not fully readable")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        proc.stdout.close()


def safe_member_path(dest: str, name: str) -> str | None:
    """Where a member goes inside dest; None if its name tries to leave dest ("zip slip")."""
    parts = [p for p in name.replace("\\", "/").split("/") if p not in ("", ".")]
    if not parts or any(p == ".." or ":" in p for p in parts):
        return None
    target = os.path.abspath(os.path.join(dest, *parts))
    root = os.path.join(os.path.abspath(dest), "")
    return target if target.startswith(root) else None
