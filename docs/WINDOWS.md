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
