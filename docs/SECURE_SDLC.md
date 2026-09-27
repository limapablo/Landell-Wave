# Secure SDLC

## Change flow

1. Changes should enter through a short-lived branch and pull request.
2. CI and security-sensitive changes require explicit review.
3. Required checks should include tests and CodeQL.
4. Merge only after checks pass; do not bypass branch protection for routine changes.
5. Deploy from reviewed source, not from a developer workstation.

## Security gates

- Unit/security regression tests on every relevant change.
- CodeQL for Python and JavaScript.
- Dependency review on pull requests.
- Dependabot for GitHub Actions.
- Full commit SHA pinning for Actions.
- Explicit workflow permissions.
- CODEOWNERS for security-sensitive paths.

## Vulnerability handling

Follow `SECURITY.md`. Security reports should be triaged by impact, exploitability, affected trust boundary and whether generated artifacts must be rebuilt.

## Release/build integrity

The generated catalog is disposable output: source and build instructions are authoritative. A failed scheduled build must not destroy the last known-good published snapshot.

For a public release artifact, add cryptographic provenance/attestation and verify it as part of promotion. GitHub artifact attestations provide build provenance; private repositories require an eligible Enterprise Cloud plan.

## Repository controls to configure in GitHub

- Require pull requests before merging to `main`.
- Require at least one approval.
- Require conversation resolution.
- Require status checks.
- Block force pushes and deletion of `main`.
- Require CODEOWNERS review for protected paths.
- Keep default `GITHUB_TOKEN` permissions read-only.
- Prevent Actions from approving pull requests.
- Enable private vulnerability reporting, secret scanning/push protection and Dependabot security alerts when available.
- Restrict allowed Actions to GitHub-owned and explicitly approved/pinned Actions.

## Future architecture gate

Adding a backend, authentication, database, secrets, analytics or a stream proxy requires a new threat-model review before implementation.
