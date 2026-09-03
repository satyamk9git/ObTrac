# Security Policy

## Supported Versions

Security fixes are made against the latest tag on `main`. Older tags
(`v0.4.1-stable`, etc.) are not backported unless the issue is severe.

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Instead, report it privately via GitHub's [Security Advisories](https://github.com/satyamk9git/ObTrac/security/advisories/new)
for this repository. Include:

- A description of the vulnerability and its impact
- Steps to reproduce (a minimal repro is very helpful)
- The version/commit you tested against

We'll acknowledge reports as soon as possible and keep you updated as a fix
is developed.

## Current Known Limitations

ObTrac is designed for **self-hosted, single-operator or trusted-team**
deployments. Before exposing an instance beyond localhost or a private
network, be aware:

- **API access requires an `OBTRAC_API_KEY`** to be set (see README) — the
  backend refuses all `/api/v1/*` requests without a matching
  `Authorization: Bearer <key>` header once one is configured. If you never
  set one, the API is unauthenticated — do not expose it publicly in that
  state.
- **No per-user accounts or RBAC.** Anyone with a valid API key has full
  read/write access to all projects, LLM configs, and data. Treat the key
  the same way you'd treat a database admin password.
- **The SQL Editor is read-only**, enforced by opening the SQLite file
  itself in read-only mode at the driver level (not by keyword filtering),
  so no query phrasing can bypass it.
- **Provider API keys are encrypted at rest** (see `app/core/crypto.py`).
  Set `OBTRAC_ENCRYPTION_KEY` explicitly in any deployment you care about
  recovering — without it, a key is auto-generated and stored next to the
  database; losing that file makes existing encrypted secrets unrecoverable.
