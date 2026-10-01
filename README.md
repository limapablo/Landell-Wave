# Landell Wave

**Landell Wave** is named in tribute to Brazilian wireless-communication pioneer **Roberto Landell de Moura**, whose early experiments and patents helped advance the history of radio transmission.


A worldwide internet-radio directory designed around a simple hierarchy:

**Country → region/state → city → station**

No globe UI. No proprietary station list. The catalog is rebuilt automatically from open upstream data and can be exported as standard M3U playlists.

## What it does

- **Global station search** across the full catalog by station, city, region, tags and language.
- **Persistent local favorites** stored only on the user's device (no account or backend required).

- Presents the catalog through a compact **classic desktop UI**, inspired by stable Windows-era utilities rather than modern dashboard styling.

- Browses working radio streams by **country, administrative region and city**.
- Uses **Radio Browser** as the global station/stream source.
- Uses station coordinates plus **GeoNames** for offline city enrichment.
- Keeps uncertain locations as `Unknown city` instead of inventing a place.
- Filters by station name, tag, language and minimum bitrate.
- Plays streams directly in the browser when the stream/CORS/browser codec allows it.
- Exports the current filtered selection as `.m3u`.
- Generates `world.m3u` and one playlist per country.
- Rebuilds automatically every day with GitHub Actions.
- Publishes the generated static site and data to an orphan `gh-pages` branch, preventing catalog history from bloating the source branch.

## Architecture

```text
Radio Browser API
       │
       ├── station name / stream / codec / bitrate / tags / language
       └── country / state / coordinates
                         │
                         ▼
                 build_catalog.py
                         ▲
                         │
GeoNames cities1000 ─────┘
GeoNames admin1 codes
                         │
                         ▼
              Static catalog snapshot
       ┌─────────────────┼───────────────────┐
       ▼                 ▼                   ▼
country JSON        country M3U          world.m3u
       │
       ▼
static web UI: Country → Region → City → Station
```

## Repository layout

```text
.
├── src/
│   └── build_catalog.py
├── tests/
│   └── test_build_catalog.py
├── public/
│   ├── index.html
│   └── assets/
│       ├── app.js
│       └── styles.css
└── .github/workflows/
    ├── build-and-deploy.yml
    └── test.yml
```

Generated `public/data/` and `public/playlists/` are deliberately ignored on `main`. The daily workflow publishes a clean generated snapshot to `gh-pages`.

## Windows app

Landell Wave can also be installed as a native Windows desktop application. The Windows CI build produces both an **NSIS setup executable (.exe)** and a **WiX installer (.msi)** plus SHA-256 checksums.

See [Windows desktop build](docs/WINDOWS.md).

## Run locally

Requirements: Python 3.12+ and internet access for the data build.

```bash
git clone https://github.com/limapablo/Landell-Wave.git
cd Landell-Wave
make test
make build
make serve
```

Then open `http://localhost:8000`.

### Reopen it later on Windows

After the first catalog build, you normally only need to start the local server again:

```powershell
cd C:\path\to\Landell-Wave
py -3 -m http.server 8000 --directory public
```

Then browse to `http://localhost:8000`. Keep the terminal window open while the local web version is running.

For a double-click launcher and catalog update instructions, see [Windows desktop build and local usage](docs/WINDOWS.md).

Equivalent build command:

```bash
python3 src/build_catalog.py --output public --cache .cache --clean-generated
```

Useful options:

```bash
python3 src/build_catalog.py --station-limit 100000 --max-city-distance-km 80
```

## Generated output

After a build:

```text
public/
├── data/
│   ├── index.json
│   ├── sample.json
│   └── countries/
│       ├── BR.json
│       ├── IT.json
│       ├── US.json
│       └── ...
└── playlists/
    ├── world.m3u
    └── countries/
        ├── BR.m3u
        ├── IT.m3u
        ├── US.m3u
        └── ...
```

The web interface can also export a selection such as:

`Brazil → Rio de Janeiro → Rio de Janeiro`

as a new M3U file directly in the browser.

## How city matching works

Radio Browser exposes country/state metadata and optional station coordinates, but not a consistent universal city field. The build therefore:

1. downloads the global `cities1000` GeoNames dataset;
2. indexes cities in geographic buckets by country;
3. finds the nearest city to each geolocated station;
4. accepts the city only when it is in the same country and within the distance threshold (80 km by default);
5. preserves `Unknown city` when there is not enough evidence.

This intentionally favors **honest unknowns over fake precision**.

## Security architecture

The project follows a security-first static architecture:

- upstream radio/place data is treated as untrusted;
- build-time downloads and generated paths are bounded and validated;
- local/private network destinations are rejected when identifiable;
- generated artifacts receive an independent validation pass;
- the untrusted-data build job has read-only repository access;
- publication occurs in a separate privileged job;
- GitHub Actions are pinned to immutable commit SHAs;
- the browser uses a restrictive CSP and safe DOM text APIs;
- third-party station images are not loaded passively.

See:

- [Architecture](docs/ARCHITECTURE.md)
- [Threat model](docs/THREAT_MODEL.md)
- [Security policy](SECURITY.md)
- [Secure SDLC](docs/SECURE_SDLC.md)
- [Risk register](docs/RISK_REGISTER.md)

## Automation

`build-and-deploy.yml` runs:

- on every relevant push to `main`;
- manually through `workflow_dispatch`;
- once per day at `06:23 UTC`.

It runs the tests, rebuilds the entire catalog, and force-publishes a clean snapshot to `gh-pages`.

To expose the web UI publicly, set GitHub Pages to serve the **`gh-pages` branch / root** in repository settings. The generated branch is created automatically by the first successful build.

## Data sources and attribution

Station metadata and streams come from **Radio Browser**, a community-maintained internet-radio database. The project sends a descriptive User-Agent and requests only working stations (`hidebroken=true`).

City/place enrichment uses **GeoNames**, whose gazetteer data is distributed under a Creative Commons Attribution license. See the GeoNames terms for the applicable dataset attribution requirements.

This repository does **not** own or rebroadcast the radio streams. Availability, rights and geographic restrictions remain the responsibility of each station/stream provider.

## License

The project code is licensed under the MIT License. Upstream radio metadata, station content and GeoNames data retain their respective licenses and terms.
