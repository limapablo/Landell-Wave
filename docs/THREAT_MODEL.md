# Threat Model

## Scope

Landell Wave is a static web application plus a scheduled data-ingestion/build pipeline. It does not authenticate end users, accept user-generated content directly, proxy streams, or operate an application backend.

## Assets

1. Integrity of source code and CI/CD configuration.
2. Integrity of the generated catalog and playlists.
3. GitHub repository write capability and `GITHUB_TOKEN`.
4. Trust users place in links and streams exposed by the application.
5. Availability of the build and published catalog.

## Trust boundaries

- GitHub repository → GitHub-hosted runner.
- GitHub-hosted runner → Radio Browser.
- GitHub-hosted runner → GeoNames.
- Generated JSON → browser.
- Browser → arbitrary radio stream providers.
- Browser → station homepages and favicon hosts.

All data crossing an external boundary is untrusted.

## Principal threats and controls

| Threat | Example | Controls |
|---|---|---|
| Supply-chain compromise | Mutable or compromised CI Action | Full-SHA pinning, Dependabot, minimal Actions surface |
| CI privilege abuse | Build step gains repository write | Explicit permissions; write permission exists only where publishing requires it |
| Path traversal | Malicious country code becomes output path | Strict two-letter country-code normalization |
| Malicious URLs | `javascript:` homepage or credential-bearing URL | Scheme/credential validation at build and browser boundaries |
| XSS | Station metadata contains HTML/script | DOM `textContent`, no metadata `innerHTML`, CSP |
| Resource exhaustion | Oversized API response/ZIP bomb | HTTP payload and uncompressed archive limits |
| Discovery poisoning | Rogue Radio Browser mirror | Mirror hostname allowlist pattern + HTTPS |
| HTTPS downgrade | Redirect to insecure build endpoint | Reject downgrade for build-time downloads |
| Malicious playlist metadata | CR/LF/quote injection | M3U metadata escaping and line normalization |
| Stream risk | Legacy HTTP or hostile media endpoint | Browser sandbox model; no server-side proxy/fetch; user initiates playback |
| Availability attack | Upstream unavailable | Mirror fallback, retries, timeout, last published static snapshot remains available |

## Explicit non-goals

- Guaranteeing that third-party radio content is benign, legal, accurate, or continuously available.
- Inspecting or proxying arbitrary stream payloads.
- Hiding a user's IP address from a station they choose to play.
- Treating Radio Browser votes or metadata as authoritative identity verification.

## Residual risks

Legacy HTTP radio streams have weaker transport security and can be blocked as mixed content by browsers. Station favicons and streams reveal requests to their respective hosts. GitHub Pages limits control over response headers compared with a dedicated edge/server deployment.

## Review triggers

Revisit this threat model when adding authentication, a backend/proxy, analytics, user submissions, cloud credentials, databases, administrative interfaces, or third-party JavaScript.
