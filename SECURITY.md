# Security Policy

## Supported version

Security fixes are applied to the current `main` branch.

## Reporting a vulnerability

Please do not open a public issue for a suspected vulnerability.

Use GitHub's private vulnerability reporting feature for this repository when available. Include:

- affected component and commit;
- reproduction steps or proof of concept;
- expected impact;
- suggested mitigation, if known.

Do not include secrets, personal data, or destructive test output.

## Security model

Landell Wave is a static catalog and browser client. Radio Browser and GeoNames are external trust boundaries. Their data is treated as untrusted input.

The project:

- validates build-time remote endpoints and rejects HTTPS downgrade redirects;
- bounds remote payload and GeoNames archive sizes;
- validates country codes before using them in generated paths;
- restricts browser-visible external homepage/favicon URLs to HTTPS;
- does not use `innerHTML` for station metadata;
- applies a restrictive Content Security Policy;
- pins GitHub Actions to immutable commit SHAs;
- grants GitHub Actions only the permissions required by each workflow.

Radio stream URLs may use HTTP because many legacy internet-radio stations do not provide HTTPS. Browsers may block those streams when the site itself is served over HTTPS; the project does not proxy them.
