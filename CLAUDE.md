# DupFinder — project context

Reply in **the language the user writes in** (Italian or English): match the language of their latest message. The tool's interface, code comments and documentation are in English.

## Long-term goal
A **cross-platform** tool (Windows, macOS, Linux) to tidy up backups scattered across the computer:
1. **Inventory**: file statistics (by type, size, age, folder, oldest and largest).
2. **Deduplication** by content (hash), never by name.
3. **Archiving**: periodic zips holding only unique files, with a catalog (SQLite) that remembers original paths and destination archive, plus restore.
4. **Move check**: a watcher or "inbox" folder that flags whether a file is already archived.

The user uses OneDrive but does not want to upload everything there: they prefer compressed local archives.
The user wants a **real local desktop app**, not a site relying on a backend, with the option to run as **administrator** to delete protected files.

## Current state: `dupfinder/` package (all four modules)
Python 3.8+, no mandatory dependencies. Runs as a **desktop app** (pywebview window, API through the JS bridge, no HTTP API) when `pywebview` is installed, otherwise in the browser (local server).

```
python start.py                           # build the React frontend + start (desktop window if pywebview is installed)
python start.py D:\Foto                   # arguments are passed to python -m dupfinder
python -m dupfinder --browser             # force browser mode;  --no-browser: browser mode without opening it
python -m dupfinder --admin               # Windows: relaunch elevated (UAC)
cd frontend && npm run dev                # development with hot reload: backend started with --no-browser on :8765
python build_app.py [--onedir]            # PyInstaller package → dist/DupFinder.exe (tested: ~21 MB, opens the window)
pip install -e .[all]  →  dupfinder ...   # optional: installs the command with pywebview, Pillow, send2trash
python -m unittest                        # tests
```

Optional: `pywebview` (desktop window), `Pillow` (similar images, thumbnails), `send2trash` (Recycle Bin), 7-Zip for 7z/RAR (`DUPFINDER_7ZIP` for a non-standard path).
`DUPFINDER_HOME` (default `~/.dupfinder`) and `DUPFINDER_QUARANTINE` (default `~/DupFinder_Quarantine`) move the data: used for portable copies and for UI tests that must not touch the user's data.

### Features
- **Deduplication**: content duplicates in 3 steps (size → quick hash of first + last 64 KB → full BLAKE2b), also inside ZIP/7z/RAR (streaming, up to `MAX_NEST` = 10 levels; inner hashes cached in `archive_cache.json`; Deflate64 zips fall back to 7-Zip). Disk-file hashes are cached in the SQLite catalog (`hashes` table, valid while size+mtime are unchanged): later scans only read changed files ("from cache" pill).
- Review: tree, copies with preview (image thumbnail or text), "Keep only this one", "Keep / Delete here", strategies (oldest, newest, shortest, longest, **"Delete disk copies already in an archive"**), **preferred folders** (first matching folder wins, strategy breaks ties), preview of what Apply changes, filter, **CSV export**.
- **"Copies in archives count as kept"** option (`arc_keep`): a group may lose all disk copies if a copy is inside an archive that is still exactly the one scanned (size + mtime of the outer archive).
- **Archive extraction** (`extract.py`): plan first (files, already on disk, space needed vs free), skip members with an intact identical copy on disk (hash verified while reading), never overwrite (" (1)" suffix, or skip if identical), then optionally move the archive to quarantine/trash only if everything succeeded. Handled: not enough space (before starting, with `SPACE_MARGIN`), disk full mid-way (partial file removed, archive kept), access denied, zip slip names (refused), encrypted members, damaged archives, archive changed since the scan, cancellation.
- **Similar folders** (`inventory.similar_folders`): pairs of folders (also folders inside archives) where ≥ 50% of the files of A have a copy in B; files directly inside each folder only.
- **Similar images** (`images.py`, needs Pillow): 64-bit dHash, groups with Hamming distance ≤ 4 (5-chunk pigeonhole buckets + union-find), groups made only of identical copies are skipped, best = highest resolution then size; dHash cached in `hashes.phash`.
- **Inventory**: collected during the walk (per thread, merged): by extension, by year, per folder (depth ≤ `INVENTORY_DEPTH` with recursive totals), top 100 largest and oldest.
- **Catalog** (`catalog.py`, `~/.dupfinder/catalog.db`): incremental zips (`DupFinder_<date>.zip`, only content not yet catalogued, duplicates stored once, compressed formats stored), zip read back and hashed before being recorded (catalog stores what is really in the zip); search by path or hash; restore to the original place or another folder (hash checked, never overwrites); verify; forget. Archives remember the **volume serial** so a disk that changes letter is found again.
- **Quarantine** (`quarantine.py`): each deletion session writes `manifest.json` (original, stored, size, mtime); list, restore (never overwrites), purge. Old sessions without manifest and the old `DupFinder_Cestino` folder are read too.
- **Inbox watcher** (`watcher.py`): polls folders every `WATCH_INTERVAL` s; a file is checked once stable; result archived / copy on disk / not archived. Restarts with the app (settings).
- **Session**: results + selection saved in `session.json` and reloaded at start (survives the admin relaunch). Settings in `settings.json`.
- **Administrator**: "Restart as admin" (Windows, `ShellExecuteW runas`, current process exits); read-only files are deletable anyway (attribute cleared); "Access denied" errors suggest the relaunch.
- Deletion to the Recycle Bin, quarantine or permanent.

### Decisions made (to respect)
- **Files inside archives are never deleted** (no checkbox). By default they **do not count as a copy to keep**; with `arc_keep` they do, only if the outer archive is unchanged since the scan (checked on the server at deletion time).
- Before deleting, the server checks that the file and at least one copy to keep still have the size and date from the scan.
- Only `.zip`, `.7z` and `.rar` are archives: `.docx`, `.xlsx`, `.jar` etc. are not opened. `.partN.rar` volumes with N>1 are skipped.
- 7z and RAR go through the 7-Zip command line (`archives.list_7z`: `l -slt -ba`, then a single `x -so` split using the listing sizes). If the stream does not add up, the archive is discarded and reported. A dummy password avoids hanging on encrypted archives. While extracting, a member that fails is still read to the end so the stream stays aligned.
- Nested ZIP archives stay in memory up to 64 MB (then a temporary file); nested 7z and RAR use a temporary file deleted right after.
- Security: browser mode listens only on 127.0.0.1 with a Host header check and a random token; the desktop app exposes no HTTP API (pywebview's own loopback server only serves the static build). Quarantine session ids are validated (no path traversal); previews only for files in the scan results.
- No zip bomb protection: the user said they have none.
- **Multi-threaded**: `_walk` lists folders with `IO_WORKERS` threads (1 if every root is on an HDD); `Scanner._parallel` hashes and reads archives with one pool per disk (`IO_WORKERS` on SSD, 1 on HDD). HDDs detected on Windows with PowerShell `Get-PhysicalDisk` (cached). Counters and errors under `_mlock`; per-archive errors in `_tls`.
- The desktop app uses the user agent `DupFinderApp`: `api.js` then calls `window.pywebview.api.call(method, path, body)` instead of `fetch`; both transports go through `api.route()`.

### Structure
Backend (`dupfinder/`):
- `config.py`: constants (exclusions, system folders, archives, `DATA_DIR`, quarantine, image/text extensions, `SPACE_MARGIN`…).
- `utils.py`: 7-Zip, `archive_kind`, `StreamHasher`, roots, reveal, `file_hash`, `describe_os_error`/`is_disk_full`, `remove_file`/`move_file` (read-only aware), `is_admin`/`relaunch_as_admin`, volume serials (`volume_info`, `find_on_volume`).
- `archives.py`: `list_7z`, `members`, `iter_members` (zip / 7-Zip streams), `safe_member_path`.
- `scanner.py`: `Scanner`: `_walk` (threads, inventory) → `_scan_archives` → `_find_duplicates` (hash cache) → `_build_results`; `delete(ids, mode, arc_keep, similar)`; `save_session`/`load_session`/`set_selection`.
- `catalog.py`: `Catalog` (hash cache + archives), `archive_job`, `verify_job`, `restore_job`, `CATALOG`.
- `extract.py`: `plan`, `extract_job`.  `images.py`: `similar_job`, `thumbnail`.  `inventory.py`: `Inventory`, `similar_folders`.
- `quarantine.py`, `watcher.py`, `jobs.py` (background jobs with progress/cancel, one per kind).
- `api.py`: `route(method, path, data)` → (status, body, content type): all endpoints; `SCANNER`, `WATCHER`, settings, `startup()`.
- `server.py`: HTTP `Handler` (static build with `STATIC_RE`, token, Host check) → `api.route`.  `app.py`: pywebview window + `Bridge` (`call`, `pick_folder`, `save_text`).  `__main__.py`: command line.
- Root: `start.py` (npm build + start), `build_app.py` + `dupfinder_app.py` (PyInstaller).

Frontend (`frontend/`, React 19 + Vite, JSX): `App.jsx` (views, scan polling, selection saved to the server, strategies/rules, arc_keep, export, dialogs), `tree.js` (pure logic: tree, `statusOf`, `keepDir`, `deleteDir`, `applyStrategy` with preferred folders, `diffSelection`, `toCsv`), `api.js` (two transports, `apiBlob`, `pickFolder`, `saveText`), `format.js`.
- `components/`: `Sidebar` (navigation, counts, admin), `ScanPanel`, `Progress`, `Summary`, `Tree`, `Inspector` (+ `Preview`), `DeleteDialog`, `ExtractDialog`, `Job` (`useJob`, `JobProgress`, `FolderField`), `Icons`.
- `views/`: `Folders`, `Images`, `Inventory`, `Catalog`, `Quarantine`, `Watcher`.
- Design: Stitch design system **"Pro Desktop Utility Engine"** (Stitch project id `18065566598976937349`; full spec in `DESIGN.md`): dark theme, Geist + JetBrains Mono, tokens in `:root` of `styles.css`. Fixed color roles: cyan action/selection, emerald kept/unique, amber duplicate, violet archive, red deletion.

Tests: `tests/test_scanner.py` (base class `Isolated` redirects caches, catalog, session and quarantine to a temp folder — new tests must use it), `tests/test_features.py` (arc_keep, quarantine, session, hash cache, inventory, similar folders, catalog, extraction incl. 7z/zip slip/disk full/no space, similar images, watcher, routes), `tests/test_server.py`.

## Git and releases
Commit messages use **Conventional Commits** (`feat:`, `fix:`, `docs:`, `ci:`…): release-please reads them.
`.github/workflows/release.yml`: on every push to `main` release-please updates the Release PR (`CHANGELOG.md`, version in
`pyproject.toml` + `frontend/package.json`, config in `release-please-config.json` / `.release-please-manifest.json`);
merging it creates tag + release, then Windows/macOS builds are attached. Never edit the version or CHANGELOG by hand.

## Tests done (repeat after changes)
- `python -m unittest`: 30 tests (Windows, Python 3.15, 7-Zip, Pillow).
- Interface in browser mode with Chrome DevTools on a demo folder: scan, preview, extraction (5 of 6 skipped, archive to quarantine), similar folders, inventory, similar images, catalog (archive, search, restore elsewhere, verify), quarantine restore, watcher, "archived" strategy + arc_keep deletion; no console errors.
- Desktop app: pywebview window driven by script (bridge calls, scan, data-URL previews); packaged `DupFinder.exe` opens its window.
- Earlier on Linux with 7-Zip 24.09: nested archives to level 10/11, encrypted/truncated archives reported, `.docx` not opened, no leftover temporary files, API without token or with another Host → 403.

## Known limits
- **RAR has not really been tested**, but it goes through the same path as 7z.
- "Restart as admin" not tested end to end (needs the UAC click); POSIX: start with sudo.
- The watcher only knows hashed files (archived ones and the duplicate candidates of the scans).
- Similar folders: direct files only, and the list is not updated after deletions until the next scan.
- With millions of files the size map is held in memory; the session file holds every image path.
- HDD detection: Windows tested; Linux `/sys/.../rotational` untested; macOS treated as SSD. Volume serials: Windows tested, macOS (diskutil) and Linux (/dev/disk/by-uuid) untested.
- With many nested zips in parallel, memory can reach `IO_WORKERS × 64 MB`.
- Similar images: thresholds fixed (`SIMILAR_MAX_DIST`), HEIC not supported (Pillow without plugins).

## Possible next steps
- Installer / code signing for the packaged app; app icon.
- Show similar-image and similar-folder results updated after deletions without a rescan.
- Watcher: OS notifications; "archive the new inbox files" in one click.
