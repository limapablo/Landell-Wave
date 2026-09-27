# Architecture

## Security-first data flow

```text
                Internet / untrusted zone
        ┌───────────────────────────────────┐
        │ Radio Browser      GeoNames       │
        └───────────┬───────────┬───────────┘
                    │ HTTPS      │ HTTPS
                    ▼            ▼
              ┌──────────────────────┐
              │ Ingestion boundary   │
              │ size / scheme / host │
              │ validation           │
              └──────────┬───────────┘
                         ▼
              ┌──────────────────────┐
              │ Normalization layer  │
              │ bounded text/numbers │
              │ URL + path policy    │
              └──────────┬───────────┘
                         ▼
              ┌──────────────────────┐
              │ Catalog generation   │
              │ JSON + M3U + hashes  │
              └──────────┬───────────┘
                         ▼
              ┌──────────────────────┐
              │ Artifact validation  │
              │ schema / links /     │
              │ counts / file types  │
              └──────────┬───────────┘
                         │
                 GitHub artifact
                         │
              privilege boundary
                         ▼
              ┌──────────────────────┐
              │ Publish job          │
              │ contents: write      │
              │ no artifact execute  │
              └──────────┬───────────┘
                         ▼
                     gh-pages
                         │
                         ▼
              ┌──────────────────────┐
              │ Static browser app   │
              │ CSP + no innerHTML   │
              │ user-initiated media │
              └──────────────────────┘
```

## Design principles

### Default deny
Unknown protocols, malformed identifiers, local-network destinations, unsafe output paths, unexpected files, and malformed archives are rejected.

### Least privilege
The build job processes the internet-facing data but has only `contents: read`. Repository write permission exists only in the isolated publish job.

### Dependency minimization
The application runtime and build logic use the Python standard library and browser platform APIs. External GitHub Actions are pinned to immutable SHAs.

### Explicit trust boundaries
Radio Browser, GeoNames, station metadata, generated artifacts, and station URLs are not implicitly trusted.

### Privacy by default
Third-party station favicons are not loaded automatically. External communication happens only for catalog build operations or user-initiated navigation/media playback.

### Fail closed
A malformed or suspicious catalog causes the build to fail rather than publishing a degraded or unexpectedly shaped artifact.

## Components

### `src/build_catalog.py`
Downloads, validates, normalizes and enriches upstream radio data.

### `src/validate_output.py`
Independent post-build validator. It verifies output shape, station counts, URLs, file types and playlist invariants before publication.

### `src/security_lint.py`
Dependency-free security policy enforcement for source code and CI configuration.

### Static browser application
Consumes generated JSON only. Upstream text is rendered through safe DOM text APIs. Media playback is explicit and user-initiated.

## Operational model

The product is intentionally static: there is no application server, session store, user database, authentication layer or long-lived application secret. This substantially reduces attack surface and operational complexity.

The main remaining external attack surfaces are supply-chain integrity, upstream data poisoning, browser media parsers, DNS rebinding, and repository administration.
