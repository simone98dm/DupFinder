# Setup

Everything needed to run, test and package DupFinder from the sources on Windows, macOS and Linux.

## Requirements

| Tool | Version | Needed for |
|---|---|---|
| **Python** | 3.8+ (3.12 recommended) | the app itself (standard library only) |
| **Node.js + npm** | 20.19+ (22 LTS recommended) | building the interface (React + Vite) |
| Git | any | cloning the repository, commits |

Optional:

| Tool | Install | Without it |
|---|---|---|
| `pywebview` | `pip install pywebview` (Linux: `pip install "pywebview[qt]"`) | DupFinder opens in the browser instead of its own window |
| `Pillow` | `pip install Pillow` | no similar images, no image thumbnails |
| `send2trash` | `pip install send2trash` | no deletion to the Recycle Bin (quarantine is the default) |
| **7-Zip** | see below | 7z and RAR archives are skipped (ZIP still works) |
| `pyinstaller` | `pip install pyinstaller` | only needed to package the app |

7-Zip: Windows <https://www.7-zip.org/> (found in `Program Files` automatically) · macOS `brew install sevenzip` ·
Debian/Ubuntu `sudo apt install 7zip` (older releases: `p7zip-full`) · Fedora `sudo dnf install p7zip p7zip-plugins`.
In a non-standard location, point `DUPFINDER_7ZIP` to the executable.

## Quick start

### Windows (PowerShell)

```powershell
git clone <repository-url> dupfinder
cd dupfinder
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install pywebview Pillow send2trash
python start.py                      # builds the interface and opens DupFinder
python start.py D:\Photos E:\        # ...and scans these folders right away
python -m dupfinder --admin          # restart as administrator (UAC) to delete protected files
```

If PowerShell blocks `Activate.ps1`: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or call
`.venv\Scripts\python.exe` directly. The window uses WebView2, already part of Windows 10/11.

### macOS and Linux

```bash
git clone <repository-url> dupfinder
cd dupfinder
scripts/run.sh                       # first run: creates .venv, installs the extras, builds the interface, opens DupFinder
scripts/run.sh ~/Photos /Volumes/Backup
scripts/run.sh --browser             # use the browser instead of the window
```

`scripts/run.sh` takes the same options as `python -m dupfinder` and installs the extras once (marker
`.venv/.installed`; delete `.venv` to start over). `PYTHON=python3.12 scripts/run.sh` uses another interpreter.

System packages, Debian/Ubuntu:

```bash
sudo apt install python3 python3-venv 7zip          # run
sudo apt install libpython3-dev binutils            # only to package the app (PyInstaller)
```

Node.js 20.19+ is often newer than the distribution's package: use <https://nodejs.org>, `nvm` or NodeSource.
macOS: `brew install python node sevenzip`.

On Linux the window uses Qt (`pywebview[qt]`, installed from pip by the script). With a GTK desktop you can use
the system WebKit instead: `sudo apt install python3-gi gir1.2-webkit2-4.1` and a venv created with
`--system-site-packages`. Without a desktop session (SSH, containers) use `--browser` or `--no-browser`.

To delete files owned by another user, start with `sudo` in browser mode
(`sudo .venv/bin/python -m dupfinder --browser`): "Restart as admin" exists on Windows only.

## Command line

```
python -m dupfinder [folders…] [options]
  --browser        use the browser instead of the desktop window (default when pywebview is missing)
  --no-browser     browser mode without opening the browser (server only)
  --port N         browser mode: local port (default 8765; a free one is picked if busy)
  --no-archives    do not look inside zip, 7z and rar
  --admin          Windows: restart as administrator
  --debug          desktop window: enable the developer tools
```

`python start.py [same options]` rebuilds the interface first (needed after every frontend change);
`python -m dupfinder` uses the last build in `dupfinder/web/`.

## Data and environment variables

| Variable | Default | Content |
|---|---|---|
| `DUPFINDER_HOME` | `~/.dupfinder` | `catalog.db` (catalog + hash cache), `session.json`, `settings.json`, `archive_cache.json` |
| `DUPFINDER_QUARANTINE` | `~/DupFinder_Quarantine` | deleted files kept for restore |
| `DUPFINDER_7ZIP` | searched in `PATH` and standard folders | 7-Zip executable |

Set both data variables to a temporary folder to try things without touching your real data.

## Development

Two terminals:

```bash
python -m dupfinder --no-browser      # backend in browser mode on 127.0.0.1:8765
cd frontend && npm install && npm run dev   # interface with hot reload (Vite proxies /api to the backend)
```

Open the address printed by Vite. Code layout and design decisions are described in `CLAUDE.md`, the design
system in `DESIGN.md`.

## Tests

```bash
python -m unittest -v          # 30 tests; 7z and similar-image tests are skipped without 7-Zip / Pillow
```

Tests use temporary folders (base class `Isolated` in `tests/test_scanner.py`) and never touch `~/.dupfinder`.

## Packaging the desktop app

| OS | Command | Result |
|---|---|---|
| Windows | `pip install pyinstaller` then `python build_app.py` | `dist/DupFinder.exe` (one file, ~21 MB) |
| macOS | `scripts/build.sh` | `dist/DupFinder.app` |
| Linux | `scripts/build.sh` | `dist/DupFinder/DupFinder` (folder, ~500 MB because of Qt WebEngine) |

`python build_app.py --onedir` builds a folder instead of a single file (starts faster). Builds are not signed:
Windows SmartScreen and macOS Gatekeeper ask for confirmation the first time (macOS: right-click → Open).

## Commits and releases

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/): `feat: …`, `fix: …`,
`docs: …`, `ci: …`, `feat!: …` for breaking changes. On every merge to `main` GitHub Actions
(`.github/workflows/release.yml`) runs release-please, which keeps a Release PR with the next version and
`CHANGELOG.md`; merging that PR publishes the release with the Windows and macOS builds.
Do not edit the version or `CHANGELOG.md` by hand.

The repository setting *Settings → Actions → General → Allow GitHub Actions to create and approve pull requests*
must be enabled for the Release PR to be opened.

## Troubleshooting

| Problem | Fix |
|---|---|
| `npm not found` | install Node.js and reopen the terminal |
| Opens in the browser instead of a window | `pywebview` missing or no GUI toolkit (Linux): see above |
| `7-Zip not found`, 7z/RAR archives skipped | install 7-Zip or set `DUPFINDER_7ZIP` |
| `Access denied` while deleting | Windows: "Restart as admin" in the sidebar; macOS/Linux: `sudo`, browser mode |
| Port 8765 busy | a free port is picked automatically, or `--port N` |
| PyInstaller: `libpython3.x.so` not found | `sudo apt install libpython3-dev` |
| `Could not create .venv` | `sudo apt install python3-venv` |
