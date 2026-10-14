"""
DupFinder - tidies up scattered backups: duplicates by content (also inside ZIP, 7z and RAR
archives), similar folders and images, inventory, an SQLite catalog of incremental zip archives,
quarantine with restore, and an inbox watcher.

Usage:
    python -m dupfinder                    desktop window (with pywebview) or browser
    python -m dupfinder D:\Foto E:\       immediately scans these folders
    python -m dupfinder --browser --port 9000 --no-archives
    python -m dupfinder --admin            Windows: restart as administrator

Requirements: Python 3.8 or later, no external libraries.
Optional: pywebview (desktop window), Pillow (similar images, thumbnails),
send2trash (Recycle Bin), 7-Zip (7z and RAR; DUPFINDER_7ZIP for a non-standard path).
"""
