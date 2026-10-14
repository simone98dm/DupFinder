"""Helpers: 7-Zip, archive type, streaming hashes, paths."""
from __future__ import annotations

import ctypes
import errno
import hashlib
import os
import plistlib
import shutil
import stat
import string
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from .config import IS_MAC, IS_WIN, NO_WINDOW, PARTIAL, READ_BUF, _RAR_PART

try:
    from send2trash import send2trash as _send2trash
except ImportError:  # optional
    _send2trash = None


class Cancelled(Exception):
    pass


def find_7zip() -> str | None:
    env = os.environ.get("DUPFINDER_7ZIP")
    if env and os.path.isfile(env):
        return env
    for name in ("7z", "7zz"):
        p = shutil.which(name)
        if p:
            return p
    candidates = []
    if IS_WIN:
        for var in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
            base = os.environ.get(var)
            if base:
                candidates.append(os.path.join(base, "7-Zip", "7z.exe"))
    elif IS_MAC:
        candidates += ["/opt/homebrew/bin/7zz", "/usr/local/bin/7zz", "/opt/homebrew/bin/7z", "/usr/local/bin/7z"]
    return next((c for c in candidates if os.path.isfile(c)), None)


SEVENZIP = find_7zip()


def archive_kind(name: str) -> str | None:
    """Archive type from the extension (.docx, .xlsx, .jar... are not treated as archives)."""
    n = name.lower()
    if n.endswith(".zip"):
        return "zip"
    if n.endswith(".7z"):
        return "7z"
    if n.endswith(".rar"):
        m = _RAR_PART.search(n)
        if m and int(m.group(1)) > 1:
            return None          # volumes after the first: 7-Zip reads them starting from the first
        return "rar"
    return None


class StreamHasher:
    """Computes both the quick hash (head+tail) and the full hash in a single pass,
    with the same results as reading the file from disk."""
    __slots__ = ("full", "head", "tail", "small", "size")

    def __init__(self) -> None:
        self.full = hashlib.blake2b(digest_size=20)
        self.head = bytearray()
        self.tail = bytearray()
        self.small: bytearray | None = bytearray()
        self.size = 0

    def update(self, b) -> None:
        self.full.update(b)
        self.size += len(b)
        if self.small is not None:
            self.small += b
            if len(self.small) > 2 * PARTIAL:
                self.small = None
        if len(self.head) < PARTIAL:
            self.head += b[:PARTIAL - len(self.head)]
        self.tail += b
        if len(self.tail) > 4 * PARTIAL:
            del self.tail[:-PARTIAL]

    def digests(self) -> tuple[str, str]:
        if self.small is not None:
            partial = hashlib.blake2b(bytes(self.small), digest_size=20).hexdigest()
        else:
            h = hashlib.blake2b(digest_size=20)
            h.update(self.head)
            h.update(self.tail[-PARTIAL:])
            partial = h.hexdigest()
        return partial, self.full.hexdigest()


class _ExactReader:
    """Reads exactly n bytes from a stream, flagging it if the stream ends early."""

    def __init__(self, f, n: int) -> None:
        self.f, self.n, self.short = f, n, False

    def __iter__(self):
        while self.n > 0:
            b = self.f.read(min(READ_BUF, self.n))
            if not b:
                self.short = True
                return
            self.n -= len(b)
            yield b


def _parse_7z_time(s: str | None) -> float | None:
    try:
        return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").timestamp() if s else None
    except ValueError:
        return None


def suggested_roots() -> list[str]:
    if IS_WIN:
        return [f"{d}:\\" for d in string.ascii_uppercase[2:] if os.path.exists(f"{d}:\\")]
    roots = [str(Path.home())]
    for base in ("/Volumes", "/media", "/mnt", f"/media/{os.environ.get('USER', '')}"):
        try:
            for e in os.scandir(base):
                if e.is_dir() and e.name not in ("Macintosh HD", "Recovery") and os.path.ismount(e.path):
                    roots.append(e.path)
        except OSError:
            pass
    return list(dict.fromkeys(roots))


def normalize_roots(paths: list[str]) -> list[str]:
    """Makes paths absolute and drops those contained in others (they would be counted twice)."""
    out = []
    for p in paths:
        p = p.strip().strip('"').strip("'")
        if not p:
            continue
        p = os.path.abspath(os.path.expanduser(p))
        if not os.path.isdir(p):
            raise ValueError(f"Folder not found: {p}")
        out.append(p)
    if not out:
        raise ValueError("Enter at least one folder.")

    def key(p: str) -> str:
        return os.path.normcase(os.path.join(p, ""))

    res: list[str] = []
    for p in sorted(set(out), key=lambda x: len(key(x))):
        if not any(key(p).startswith(key(r)) for r in res):
            res.append(p)
    return res


def reveal_in_file_manager(path: str) -> None:
    if IS_WIN:
        subprocess.Popen(f'explorer /select,"{path}"')
    elif IS_MAC:
        subprocess.Popen(["open", "-R", path])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path)])


_hdd_lock = threading.Lock()
_hdd_cache: dict[tuple, set[str]] = {}


def hdd_drive_letters() -> set[str]:
    """Windows: letters of the drives that sit on a spinning disk (HDD).
    The PowerShell query takes ~3 s: the result stays valid until the mounted drives change."""
    mounted = tuple(d for d in string.ascii_uppercase if os.path.exists(f"{d}:\\"))
    with _hdd_lock:
        if mounted not in _hdd_cache:
            _hdd_cache[mounted] = _query_hdd_letters()
        return _hdd_cache[mounted]


def _query_hdd_letters() -> set[str]:
    ps = ("Get-Partition | Where-Object DriveLetter | ForEach-Object { $d = $_; "
          "Get-PhysicalDisk | Where-Object { $_.DeviceId -eq [string]$d.DiskNumber -and $_.MediaType -eq 'HDD' } "
          "| ForEach-Object { $d.DriveLetter } }")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                           stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           timeout=60, creationflags=NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return set()                     # not detectable: all treated as SSD
    return {w.upper() for w in r.stdout.split() if len(w) == 1}


def is_rotational(path: str) -> bool:
    """Linux: True if the file is on a spinning disk. macOS: always False (almost only SSDs)."""
    if IS_WIN or IS_MAC:
        return False
    try:
        st = os.stat(path)
        dev = os.path.realpath(f"/sys/dev/block/{os.major(st.st_dev)}:{os.minor(st.st_dev)}")
        for d in (dev, os.path.dirname(dev)):    # a partition has its queue in the parent disk
            f = os.path.join(d, "queue", "rotational")
            if os.path.exists(f):
                with open(f) as fh:
                    return fh.read().strip() == "1"
    except (OSError, ValueError):
        pass
    return False


def file_hash(path: str, check=None) -> str:
    """Full BLAKE2b of a file on disk: the same value as the scanner's full hash
    (and as the quick hash for files up to 2*PARTIAL bytes)."""
    h = hashlib.blake2b(digest_size=20)
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(READ_BUF), b""):
            if check:
                check()
            h.update(b)
    return h.hexdigest()


def is_disk_full(e: BaseException) -> bool:
    return isinstance(e, OSError) and (e.errno == errno.ENOSPC or getattr(e, "winerror", None) in (39, 112))


def describe_os_error(e: BaseException) -> str:
    """Short explanation of the errors the user can act on."""
    if is_disk_full(e):
        return "Disk full: free some space and try again"
    if isinstance(e, PermissionError):
        return ("Access denied: the file is protected or in use"
                + ("" if is_admin() else " (try restarting DupFinder as administrator)"))
    if isinstance(e, FileNotFoundError):
        return "File not found: it was moved or deleted"
    if isinstance(e, OSError):
        return e.strerror or str(e)
    return str(e)


def remove_file(path: str) -> None:
    """os.remove that also clears the Windows read-only attribute when it is in the way."""
    try:
        os.remove(path)
    except PermissionError:
        if not IS_WIN:
            raise
        os.chmod(path, stat.S_IWRITE)
        os.remove(path)


def move_file(src: str, dest: str) -> None:
    """shutil.move that copes with read-only files on Windows (moving across drives deletes the source)."""
    try:
        shutil.move(src, dest)
    except PermissionError:
        if not IS_WIN:
            raise
        os.chmod(src, stat.S_IWRITE)
        shutil.move(src, dest)


# ---- administrator ----
def is_admin() -> bool:
    try:
        if IS_WIN:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        return os.geteuid() == 0
    except (AttributeError, OSError):
        return False


def relaunch_as_admin(argv: list[str]) -> bool:
    """Windows: starts this program again elevated (UAC prompt). True if the new process started."""
    if not IS_WIN:
        return False
    if getattr(sys, "frozen", False):              # packaged .exe
        exe, args = sys.executable, argv[1:]
    else:
        exe, args = sys.executable, ["-m", "dupfinder", *argv[1:]]
    params = subprocess.list2cmdline(args)
    return ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, os.getcwd(), 1) > 32


# ---- volumes: external disks are recognized by serial number, not by drive letter ----
def _mount_point(path: str) -> str:
    path = os.path.abspath(path)
    while not os.path.ismount(path):
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    return path


def _volume_serial(root: str) -> tuple[str | None, str]:
    """(serial, label) of the volume mounted at root; serial None if it cannot be read."""
    try:
        if IS_WIN:
            serial, label = ctypes.c_uint32(), ctypes.create_unicode_buffer(261)
            ok = ctypes.windll.kernel32.GetVolumeInformationW(
                ctypes.c_wchar_p(root), label, 261, ctypes.byref(serial), None, None, None, 0)
            return (f"{serial.value:08X}", label.value) if ok else (None, "")
        if IS_MAC:
            r = subprocess.run(["diskutil", "info", "-plist", root], capture_output=True, timeout=10)
            info = plistlib.loads(r.stdout)
            return info.get("VolumeUUID"), info.get("VolumeName", "")
        dev = next((l.split()[0] for l in open("/proc/self/mounts", encoding="utf-8")
                    if l.split()[1] == root), None)
        if dev:
            for e in os.scandir("/dev/disk/by-uuid"):
                if os.path.realpath(e.path) == os.path.realpath(dev):
                    return e.name, os.path.basename(root)
    except (OSError, ValueError, subprocess.SubprocessError, plistlib.InvalidFileException):
        pass
    return None, ""


def volume_info(path: str) -> tuple[str | None, str, str]:
    """(serial, label, path relative to the volume root) of a path."""
    root = _mount_point(path)
    serial, label = _volume_serial(root)
    return serial, label, os.path.relpath(os.path.abspath(path), root)


def mounted_roots() -> list[str]:
    if IS_WIN:
        return [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
    if IS_MAC:
        try:
            return ["/"] + [e.path for e in os.scandir("/Volumes") if os.path.ismount(e.path)]
        except OSError:
            return ["/"]
    try:
        with open("/proc/self/mounts", encoding="utf-8") as fh:
            return [l.split()[1] for l in fh if l.startswith("/dev/")]
    except OSError:
        return ["/"]


def find_on_volume(serial: str | None, rel: str) -> str | None:
    """Where a file of a given volume is now (e.g. the external disk moved from E: to F:)."""
    if not serial:
        return None
    for root in mounted_roots():
        if _volume_serial(root)[0] == serial:
            p = os.path.join(root, rel)
            if os.path.exists(p):
                return p
    return None
