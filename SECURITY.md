# Security Policy

## Reporting a vulnerability

Do not disclose vulnerabilities, credentials, or reproducible exploit details in public issues. Use the repository host's private vulnerability-reporting feature when it is enabled. If private reporting is unavailable, open a public issue asking the maintainers for a private contact channel without including the sensitive details.

Include the affected version or commit, a minimal reproduction, impact, and any mitigation you have identified. Reports involving exposed credentials are urgent: revoke or rotate the credential at its provider immediately.

## Supported versions

Security fixes are applied to the current development branch before the first public release. Released-version support will be documented here once a stable release cadence exists.

## Deployment guidance

- Store credentials in environment variables, a secret manager, or ignored local configuration files.
- Restrict CORS origins and the optional `AUTOGIS_EXTERNAL_OUTPUT_DIR` mount before exposing the API beyond a trusted network.
- Review LLM-generated PyQGIS code before allowing it to access production data or execute in a privileged QGIS environment.