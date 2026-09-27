# Threat Model

## Scope

Global Web Radio is a static web application and build pipeline that ingests public data from Radio Browser and GeoNames, produces JSON/M3U artifacts, and publishes a read-only browser experience.

## Assets

- integrity of the generated catalog;
- integrity of the source repository and release branch;
- GitHub Actions write credentials;
- privacy of users browsing the catalog;
- user trust in station names, links, and streams;
- availability of the build pipeline.

## Trust boundaries

1. **Radio Browser** — untrusted internet input.
2. **GeoNames** — untrusted internet input.
3. **GitHub Actions runner** — ephemeral execution environment.
4. **Build artifact** — untrusted until validated.
5. **Publish job** — privileged zone with repository write permission.
6. **Browser** — hostile/untrusted network destinations supplied by catalog data.

## Primary abuse cases

### Supply-chain compromise
An upstream Action tag, dependency, mirror, or data source is compromised.

Controls:
- Actions pinned to immutable SHAs;
- minimal dependencies;
- Dependabot review;
- build job has read-only repository permissions;
- publish credentials exist only in a separate publish job.

### Path traversal / filesystem manipulation
An attacker injects path syntax into metadata used for generated filenames.

Controls:
- country codes normalized to strict ISO-style two-letter identifiers;
- output validator verifies generated paths and file types;
- publish job rejects symlinks.

### Client-side injection
Malicious station metadata attempts DOM XSS or script execution.

Controls:
- station metadata is rendered with `textContent`;
- no `innerHTML` for upstream data;
- restrictive CSP;
- external navigation limited to validated HTTPS URLs;
- `base-uri 'none'`, `form-action 'none'`, and `object-src 'none'`.

### Local-network access / client-side SSRF
Malicious stream URLs target loopback, private IPs, link-local ranges, or local hostnames.

Controls:
- build-time URL validation rejects obvious non-public destinations;
- browser re-validates user-activated stream URLs;
- credentials embedded in URLs are rejected;
- external images are not loaded automatically.

Residual risk:
A public DNS name can later resolve to a private address (DNS rebinding). A purely static client cannot reliably resolve and enforce DNS-layer policy. The application therefore never auto-fetches station streams; playback requires an explicit user action.

### Resource exhaustion
Upstream datasets are excessively large or malformed.

Controls:
- bounded HTTP reads;
- bounded ZIP uncompressed size;
- station-count cap;
- field-length limits;
- numeric range validation;
- generated artifact size checks;
- CI job timeouts.

### Catalog poisoning / integrity loss
A mirror returns a partial or maliciously modified catalog.

Controls:
- minimum expected catalog size;
- source server and SHA-256 digest stored in build metadata;
- generated output validator;
- daily rebuild from fresh sources.

## Out of scope

- security of individual radio station infrastructure;
- malicious audio payloads processed by the user's browser/media stack;
- legal/licensing status of third-party streams;
- DNS-layer enforcement that requires a trusted backend resolver or proxy.

## Security objectives

The application should fail closed on malformed metadata, avoid granting write credentials to code processing untrusted internet data, minimize automatic third-party requests, and preserve auditable build provenance.
