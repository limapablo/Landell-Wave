# Windows desktop build

Landell Wave includes a native Windows desktop wrapper built with Tauri.

## What is produced

The Windows workflow generates:

- an NSIS setup executable (`.exe`);
- a WiX installer (`.msi`);
- `SHA256SUMS.txt` for integrity verification.

The application bundles the latest validated static radio catalog from the repository's `gh-pages` branch, so the directory is available immediately after installation. Radio playback still connects directly to each station.

## Security posture

The desktop shell deliberately exposes no custom Tauri commands or plugins to the web frontend.

There is:

- no shell plugin;
- no filesystem plugin;
- no process execution API;
- no privileged IPC command surface;
- no embedded application secret;
- no application backend.

The Windows build uses SHA-pinned GitHub Actions and produces SHA-256 checksums for installers.

## Build locally on Windows

Prerequisites:

- Rust 1.88+;
- Microsoft Visual Studio C++ Build Tools;
- WebView2 (normally already present on Windows 10/11);
- Tauri CLI 2.12.

From the repository root:

```powershell
cargo install tauri-cli --version 2.12.0 --locked
cargo tauri icon src-tauri/icon-source.svg
cargo tauri build --bundles nsis,msi
```

Before a local build, `public/data/` and `public/playlists/` must contain a generated catalog snapshot.

Installers are written under:

```text
src-tauri\target\release\bundle\
```

For normal users, downloading the CI-produced installer is preferred over building locally.


## Reopening the web version on Windows

If you installed the current web version using:

```powershell
git clone https://github.com/limapablo/Landell-Wave.git
cd Landell-Wave
py -3 src\build_catalog.py --output public --cache .cache --clean-generated
py -3 -m http.server 8000 --directory public
```

the project was not installed as a native Windows application yet. The repository was cloned, the catalog was generated locally, and Python started a local web server.

After the first build, you do **not** need to rebuild the catalog every time you want to use Landell Wave.

To open it again:

```powershell
cd C:\path\to\Landell-Wave
py -3 -m http.server 8000 --directory public
```

Then open:

```text
http://localhost:8000
```

Keep the PowerShell window open while using Landell Wave. Closing that window stops the local server.

### Optional desktop launcher

For convenience, create a file named `Landell Wave.bat` on your Desktop:

```bat
@echo off
cd /d "C:\path\to\Landell-Wave"
start "" http://localhost:8000
py -3 -m http.server 8000 --directory public
```

Replace `C:\path\to\Landell-Wave` with the folder where you cloned the repository.

After that, double-clicking the BAT file will open the local Landell Wave interface in your default browser and start the required Python server.

### Updating the radio catalog

You only need to rebuild the local catalog when you want fresh station data:

```powershell
cd C:\path\to\Landell-Wave
py -3 src\build_catalog.py --output public --cache .cache --clean-generated
```

Then start the local server again.

### Native Windows version

The repository also contains a Tauri desktop wrapper and a Windows CI pipeline intended to produce native `.exe` and `.msi` installers.

Once you install one of those native packages, Python, Git, the BAT launcher, and a browser will no longer be required for normal use.


## Search and favorites

Landell Wave supports worldwide station search without selecting a country first. Type at least two characters in the search field to load the compact global search index.

Favorites are stored locally on the device using browser/WebView local storage. They are not uploaded to GitHub, Radio Browser, or any Landell Wave server. No user account is required.

The Favorites view works in both the local web version and the Tauri Windows desktop application.
