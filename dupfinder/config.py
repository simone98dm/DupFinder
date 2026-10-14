"""Constants and configuration: exclusions, system folders, archives."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

APP = "DupFinder"
IS_WIN = os.name == "nt"
IS_MAC = sys.platform == "darwin"
SEP = "\\" if IS_WIN else "/"

READ_BUF = 1024 * 1024          # 1 MB per read
PARTIAL = 64 * 1024             # bytes read at head and tail for the quick hash
# both can be moved with environment variables (portable use, tests of the interface)
QUARANTINE_ROOT = Path(os.environ.get("DUPFINDER_QUARANTINE") or Path.home() / "DupFinder_Quarantine")
LEGACY_QUARANTINE = (QUARANTINE_ROOT if os.environ.get("DUPFINDER_QUARANTINE")
                     else Path.home() / "DupFinder_Cestino")   # former name, still listed for restore
# catalog.db, session.json, settings.json (read at call time: the tests redirect it)
DATA_DIR = Path(os.environ.get("DUPFINDER_HOME") or Path.home() / ".dupfinder")

# ---- inventory, previews, similar images, extraction ----
INVENTORY_TOP = 100                        # largest / oldest files kept in the report
INVENTORY_DEPTH = 3                        # folder levels (below each root) in the space report
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
WEB_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}   # the browser shows these as they are
TEXT_EXTS = {".txt", ".md", ".csv", ".log", ".json", ".xml", ".ini", ".cfg", ".py", ".js", ".html", ".css"}
PREVIEW_MAX = 30 * 1024 * 1024             # larger images are not previewed without Pillow
SIMILAR_MAX_DIST = 4                       # max Hamming distance between 64-bit dHashes
SPACE_MARGIN = 64 * 1024 * 1024            # free space left on the disk when extracting
# already compressed: stored as-is in the catalog zips (deflate would only cost CPU)
COMPRESSED_EXTS = (IMAGE_EXTS - {".bmp", ".tif", ".tiff"}) | {
    ".zip", ".7z", ".rar", ".gz", ".bz2", ".xz", ".mp4", ".mkv", ".mov", ".avi", ".mp3",
    ".m4a", ".aac", ".ogg", ".flac", ".heic", ".docx", ".xlsx", ".pptx", ".pdf", ".jar", ".apk"}
WATCH_INTERVAL = 5                         # seconds between inbox polls
MAX_ERRORS_KEPT = 300
# reader threads per SSD (hashlib and zlib release the GIL); always 1 on HDDs
IO_WORKERS = min(8, os.cpu_count() or 4)

# ---- archives ----
MAX_NEST = 10                              # max levels of archives inside archives
ARCHIVE_SEP = " › "                        # separator shown in "virtual" paths
ZIP_SPOOL_MEM = 64 * 1024 * 1024           # nested zips up to 64 MB stay in memory
CACHE_FILE = DATA_DIR / "archive_cache.json"
CACHE_VERSION = 1
NO_WINDOW = 0x08000000 if IS_WIN else 0    # avoids the console window on Windows
_RAR_PART = re.compile(r"\.part(\d+)\.rar$", re.IGNORECASE)

# Folders excluded by name (editable from the UI)
DEFAULT_EXCLUDES = [
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "AppData", "Library", ".Trash", ".Trashes", "DupFinder_Quarantine", ".dupfinder", "$RECYCLE.BIN",
    "DupFinder_Cestino",   # former name of the quarantine folder
]

# System folders excluded by full path
WIN_SYSTEM_DIRS = {
    "\\windows", "\\program files", "\\program files (x86)", "\\programdata",
    "\\$recycle.bin", "\\system volume information", "\\recovery",
    "\\$windows.~bt", "\\$windows.~ws", "\\msocache",
}
POSIX_SYSTEM_DIRS = {
    "/proc", "/sys", "/dev", "/run", "/snap", "/boot", "/usr", "/bin", "/sbin",
    "/lib", "/lib64", "/etc", "/var", "/opt", "/private", "/System",
    "/Applications", "/Library", "/cores", "/Volumes/Recovery",
}

# "Cloud-only" file attributes (OneDrive, iCloud...): reading them would download them
WIN_PLACEHOLDER_ATTRS = 0x1000 | 0x40000 | 0x400000   # OFFLINE | RECALL_ON_OPEN | RECALL_ON_DATA_ACCESS
WIN_REPARSE_POINT = 0x400
WIN_LINK_TAGS = {0xA0000003, 0xA000000C}              # junction, symlink
MAC_SF_DATALESS = 0x40000000
