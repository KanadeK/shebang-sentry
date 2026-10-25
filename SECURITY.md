# Security

Only the latest release receives fixes. Use GitHub's private vulnerability reporting
at https://github.com/KanadeK/shebang-sentry/security/advisories/new when enabled. If that
channel is unavailable, open an issue asking for a private contact without disclosing
the vulnerability, secrets, or exploit data. Do not upload confidential inputs.

The tool operates locally, performs no network requests, and does not execute inspected
content. Reports may contain input-derived text or paths; review them before sharing.
Resource limits reduce accidental expansion but do not make this a sandbox against
hostile filesystems or concurrent file replacement. See README for exact input scope.
