# Security Risk Register

| ID | Risk | Impact | Likelihood | Current treatment | Residual risk |
|---|---|---|---|---|---|
| R-01 | Upstream catalog poisoning | High | Medium | strict normalization, output validation, source SHA-256 metadata | malicious but syntactically valid station content |
| R-02 | CI supply-chain compromise | Critical | Low/Medium | full-SHA Actions, minimal dependencies, Dependabot, least privilege | compromise of a pinned upstream commit or GitHub platform |
| R-03 | Write-token abuse during untrusted build | Critical | Low | build/publish job isolation | GitHub-hosted runner/platform compromise |
| R-04 | Path traversal in generated outputs | High | Low | strict country code policy + post-build validation | implementation defect in future code |
| R-05 | DOM XSS from station metadata | High | Low | textContent, CSP, no inline handlers, security lint | browser bug or future unsafe DOM sink |
| R-06 | Client-side local network access | High | Low/Medium | private/local literal blocking, explicit playback | DNS rebinding via public hostname |
| R-07 | User tracking through third-party resources | Medium | Low | no passive favicon loading, no-referrer | station sees user IP on explicit playback/navigation |
| R-08 | ZIP/resource exhaustion | Medium | Low | HTTP and uncompressed-size bounds, CI timeouts | highly compressed CPU-expensive malformed archive |
| R-09 | Broken/mixed-content HTTP radio streams | Low | High | documented legacy compatibility | browser may refuse playback |
| R-10 | Repository governance bypass | High | Medium until configured | CODEOWNERS, CI, Secure SDLC docs | main is unprotected until admin setting is enabled |

## Acceptance criteria

No Critical or High risk should remain untreated by design. Residual High risks that cannot be eliminated in a static client must be explicitly documented and must require user action rather than passive behavior.

## Administrative actions required

Repository settings should enforce:

- protected `main`;
- pull requests before merge;
- required passing checks;
- dismissal of stale approvals after new commits where available;
- no force-push or deletion of `main`;
- private vulnerability reporting;
- secret scanning/push protection where available;
- default Actions token permission set to read-only.
