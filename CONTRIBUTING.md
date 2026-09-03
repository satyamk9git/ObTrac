# Contributing to ObTrac

Thanks for considering a contribution.

## Development setup

```bash
git clone https://github.com/satyamk9git/ObTrac.git
cd ObTrac
python -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"

cd backend && uvicorn app.main:app --reload --port 8100 &
cd ../frontend && npm install && npm run dev
```

See [docs/setup_new_machine.md](docs/setup_new_machine.md) for the full walkthrough.

## Before opening a PR

- **Run the backend tests**: `pytest backend/tests` (see `backend/tests/README.md`
  if you're adding new ones — cover both the happy path and at least one
  failure mode).
- **Type-check**: `cd frontend && npx tsc --noEmit`
- **Lint the frontend**: `cd frontend && npm run lint`
- Keep PRs scoped to one change — separate refactors from behavior changes
  so they're reviewable independently.
- If you touch `obtrac_sdk/`, note any backward-compatibility implications
  in the PR description — the SDK is imported directly by user code, so
  breaking changes need a deprecation path (see how `@observe` was
  deprecated in favor of `@trace` for the pattern to follow).
- Update `CHANGELOG.md` for anything user-visible.

## Reporting bugs

Open a GitHub issue with:
- What you expected vs. what happened
- Your ObTrac version (`python -c "import obtrac_sdk; print(obtrac_sdk.__version__)"`)
- Steps to reproduce, ideally a minimal script

For security vulnerabilities, see [SECURITY.md](SECURITY.md) instead of
opening a public issue.

## Code style

- Python: no strict formatter enforced yet — match the surrounding file's
  style, prefer explicit over clever.
- TypeScript/React: functional components, Tailwind utility classes over
  custom CSS, keep client components (`"use client"`) unless there's a
  specific reason for server-side rendering.
