# Secure SDLC

## Change flow

1. Work is performed on a feature or security branch.
2. Pull request checks must pass.
3. Security-sensitive changes receive manual review.
4. `main` should be protected from direct pushes and force-pushes.
5. Production publishing occurs only from `main`.

## Required checks

Recommended branch protection checks:

- `Tests / test`
- `Security / static-analysis`
- dependency review for pull requests

## Dependency policy

The project intentionally minimizes runtime dependencies.

- GitHub Actions must be pinned to full commit SHAs.
- Dependency updates should arrive through Dependabot.
- Major-version changes require manual review.
- New Python or JavaScript runtime dependencies require a documented reason.

## Secrets

No application secret is required.

- GitHub Actions uses the ephemeral `GITHUB_TOKEN`.
- Default workflow permissions are read-only.
- Only the publish job receives `contents: write`.
- Secrets must never be placed in source, generated JSON, M3U files, issues, or logs.

## Release and build integrity

The build job processes untrusted internet data with read-only repository access.
The generated artifact is validated before crossing into the privileged publish job.
The privileged job does not execute files from the generated artifact.

## Incident response

For a confirmed security issue:

1. stop publishing by disabling the deployment workflow if required;
2. rotate/revoke affected credentials;
3. identify affected commits and artifacts;
4. patch on a dedicated security branch;
5. validate and release;
6. document root cause and preventive controls;
7. privately notify affected parties when appropriate.
