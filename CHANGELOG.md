# Changelog

All notable changes to ObTrac. Format roughly follows [Keep a Changelog](https://keepachangelog.com/), versions follow [Semantic Versioning](https://semver.org/).

---

## [v0.6.4] — Mustache-style prompt syntax: `{{var}}` placeholders, raw JSON in templates

**Tag:** `v0.6.4`
**Install:** `pip install "obtrac[all] @ git+https://github.com/satyamk9git/ObTrac.git@v0.6.4"`

**Breaking change for prompt templates.** Variable placeholders now use **double curly braces** (`{{varname}}`) instead of single braces (`{varname}`). Single `{` and `}` are always literal characters. This means you can paste raw JSON examples into prompts without any escaping.

### Why this change

Before v0.6.4, ObTrac used Python's `str.format()` for variable substitution. This treats `{` and `}` as variable delimiters, so any literal brace in the template (e.g. a JSON example like `Return: {"answer": "..."}`) had to be escaped as `{{` and `}}`. The dashboard validator added in v0.6.3 caught the most common mistakes, but the underlying ergonomics were still bad — anyone writing a prompt that asks the LLM to return JSON had to remember the escape rules.

v0.6.4 switches to **Mustache-style placeholders**: `{{varname}}` is the only way to mark a variable, and single `{` / `}` are always literal characters. This matches the convention used by Mustache, Handlebars, Jinja2, and most modern templating engines.

### Migration

**Existing prompts in the database use the old `{var}` syntax and will silently stop substituting variables in v0.6.4+.** They won't crash — the renderer just won't recognize the single-brace placeholders. To migrate, edit each prompt and replace `{var}` with `{{var}}` for every variable.

The dashboard validator will show a yellow warning if it detects single-brace placeholders, so you can spot which prompts need to be updated:

> *Found single-brace placeholders that look like the old syntax: `{question}`, `{context}`. In v0.6.4+ these are treated as literal text — use `{{varname}}` (double braces) instead. If these are meant to be literal characters, ignore this warning.*

There's no automated migration because the same `{name}` syntax could legitimately mean either "a variable" or "literal text" — only the user knows which.

### Changed
- **`obtrac_sdk/prompts.py`** — `Prompt.render()` now uses a regex (`re.compile(r"\{\{(\w+)\}\}")`) instead of `str.format()`. Substitutes `{{varname}}` patterns where `varname` is a Python identifier. Everything else is left alone.
- **`backend/app/api/prompts.py`** — `_extract_variables()`, `_validate_template()`, and the `/render` endpoint all updated to use the new syntax. Single-brace patterns trigger a yellow warning instead of being treated as variables.
- **`MERGE_SYSTEM_PROMPT`** — instructs the merge LLM to output `{{varname}}` style placeholders so AI-generated merged prompts follow the new convention. Uses `__SINGLE_OPEN__` / `__DOUBLE_OPEN__` placeholder markers internally to keep the rules text readable in code.
- **Frontend prompt forms** — helper text now reads *"Use `{{var}}` for variables. Single `{`/`}` are literal — paste raw JSON freely."* Variable chips in the validator green-checkmark display now show `{{var}}` style.
- **Test/Render tab** on the prompt detail page — variable input labels now show `{{varname}}`.
- **EXAMPLES.md section 11** — fully rewritten to teach the new syntax. Includes a comparison table to other templating systems and migration instructions.

### Added
- **Legacy syntax detection warning** — the validator checks for `{varname}` patterns (single brace, no escape) and warns the user that those are now treated as literal text. Soft warning, doesn't block save.

### What's NOT changed
- Existing prompts in the database are untouched. They'll show the warning when you open them in the editor, but they won't crash anything — the renderer just leaves their `{var}` placeholders as literal text.
- The SDK API is unchanged. `prompt.render(question="...", context="...")` works the same way for both syntaxes — only the template syntax inside the prompt itself is different.

---

## [v0.6.3] — Prompt template validation

**Tag:** `v0.6.3`
**Install:** `pip install "obtrac[all] @ git+https://github.com/satyamk9git/ObTrac.git@v0.6.3"`

Catches the most common prompt-template footgun: unescaped `{` and `}` characters that Python's `str.format()` interprets as variable placeholders. Most often hits users who include JSON examples in their prompts ("return your answer in this format: { ... }").

### Added
- **Backend `_validate_template()` helper** in `app/api/prompts.py` that attempts a real render with placeholder values for every declared variable. Catches `KeyError`, `IndexError`, `ValueError` from `str.format()` and returns structured error messages.
- **`POST /api/v1/prompts/validate`** standalone endpoint for live UI validation. Accepts `{"template": "..."}` and returns `{is_valid, variables, warnings, errors}`. No DB writes — pure validation.
- **Server-side enforcement**: `POST /prompts` and `POST /prompts/{name}/versions` now call `_validate_template()` before saving and return `400` with structured error details if the template can't render. Existing prompts in the DB are untouched.
- **Live validation UI** on the prompt create form (`/prompts`) and the editor tab on the detail page (`/prompts/<name>`). Debounced 400ms after the user stops typing. Renders three states: red error banner (blocks save), yellow warning banner (allows save with caution), or green checkmark with the detected variable list.
- **Save buttons disabled** when the template has rendering errors. Prevents users from creating broken prompts that fail at first render.
- **Soft warnings** for templates that look JSON-shaped but happen to render OK. Doesn't block save — just reminds the user to double-check their escaping.
- **EXAMPLES.md section 11** "Prompt template validation" documenting the brace-escape rule, the `❌ broken` vs `✓ fixed` patterns, the quick reference table, and the new auto-validation feature.

### Why this matters
Before v0.6.3, you'd write a prompt like:
```
Return JSON: {"answer": "..."}
Question: {question}
```
…save it successfully, then crash with `KeyError: '\n  "answer"'` the first time your code called `prompt.render()`. The error message gave no hint about the root cause. Now you see the error inline as you type, with a clear explanation: *"Template has an unescaped curly brace. Python tried to substitute a variable named `answer` but no such variable was declared. If you meant a literal `{` or `}` (e.g. inside a JSON example), escape them by doubling: `{{` and `}}`."*

---

## [v0.6.2] — Documentation refresh

**Tag:** `v0.6.2`
**Install:** `pip install "obtrac[all] @ git+https://github.com/satyamk9git/ObTrac.git@v0.6.2"`

Identical code to v0.6.1 — this is a docs-only release.

### Changed
- **README.md** — full rewrite for v0.6.x. Now describes the GLOBAL/PROJECT sidebar layout, lists every new feature, gives the correct tag-based install command, and has a v0.4.1-stable rollback path.
- **SETUP_NEW_MACHINE.md** — switched from "git clone + pip install -e ." to the modern `pip install "obtrac[all] @ git+...@<tag>"` flow. Covers both `v0.6.1` and `v0.4.1-stable` install commands and explains how the two versions can run side-by-side on different machines.
- **EXAMPLES.md** — added a "What's New in v0.6" section at the top covering auto-create project, async eval, AI insights at 3 levels, AI prompt regen, Excel filters, period filter, budget→alert mapping, embedder config, error logging improvements, and auto-migration. The original 15 recipes are unchanged.

### Added
- **CHANGELOG.md** (this file) — tracks every release going forward.

---

## [v0.6.1] — Release tag for new-machine deployment

**Tag:** `v0.6.1`
**Commit:** `edd50c1`
**Install:** `pip install "obtrac[all] @ git+https://github.com/satyamk9git/ObTrac.git@v0.6.1"`

Identical code to v0.6.0 (commit `170f5f7`) — this version bump exists solely to provide a clean named tag for installations to pin against. After this point we have two install paths:

- `v0.4.1-stable` — original known-good baseline
- `v0.6.1` — all M1+M2+M3-prep features

### Changed
- Bumped version in `pyproject.toml`, `obtrac_sdk/__init__.py`, and the dashboard sidebar footer.

---

## [v0.6.0] — Sidebar restructure, embedder config, async eval, AI insights, budget-alert mapping

**Tag:** *(no tag — superseded by v0.6.1)*
**Commit:** `75cf218`

### Added — Navigation
- **GLOBAL ↔ PROJECT sidebar split.** Global tools (Prompts, LLM Config, Embedder Config, DB Config, Resources, SQL Editor, Alerts) live in the top section. Project pages (Dashboard, Traces, Metrics, Analytics, Compare, Sessions, Budgets) live in the bottom and only activate after picking a project.
- **Project-aware nav disabling**: project items appear grayed out until a project is selected.
- **Landing page moved** from `app/page.tsx` to `(project)/page.tsx` so the sidebar is permanently visible everywhere.
- **Logo + favicon swap**: replaced the placeholder gradient block with `frontend/public/obtrac_logo.png`, set as favicon via Next's `app/icon.png` convention, wrapped in a circular container with object-contain so the full image is visible.

### Added — Embedder Config (M2)
- New `EmbedderConfigRecord` ORM model with auto-migration.
- Single-entry-point `app/services/embedder.py` supporting 7 providers: sentence-transformers, OpenAI, Azure OpenAI, Cohere, Vertex, HuggingFace, Ollama. Falls back to local MiniLM if no config exists.
- `/api/v1/embedder` full CRUD + `/test` endpoint that encodes a sample string.
- New `(project)/embedder/page.tsx` with provider-aware form, set-default, test, and friendly fallback banner.
- Semantic GT matcher in `resources.py` rewired to use the new service. Cache key now includes the embedder ID so switching defaults invalidates.
- New `obtrac embedder` CLI subcommand: `list`, `add`, `set-default`, `delete`, `test`.

### Added — DB Config placeholder (M3 preview)
- New `(project)/db-config/page.tsx` describes the upcoming flow: encrypted connection string, restart-required, auto-migrate schema, archive old SQLite. The full implementation is planned for v0.7.

### Added — Async eval (Phase 1)
- New `EvalJobRecord` ORM model with status lifecycle: queued → running → completed | failed | cancelled.
- Refactored synchronous eval body into `_execute_multi_llm_eval()` so both the sync and async paths share the same code.
- `POST /evaluation/run-multi-llm-async` returns a `job_id` immediately and runs the eval in a daemon thread that survives page navigation.
- `GET /evaluation/jobs` (with status filter), `GET /evaluation/jobs/{id}`, `DELETE /evaluation/jobs/{id}` (queued only — running jobs cannot be killed mid-execution from a Python thread).
- Trace detail page now uses the async endpoint, polls every 2s, and reconnects to in-flight jobs on mount via `?trace_id` query.
- New `RunningEvalsBadge` component on the layout topbar polls every 5s and shows count + dropdown of jobs with progress messages and links.

### Added — AI Insights surfaces
- **Metric Explainer** (already shipped) — diagnoses single trace failures.
- **AI Insights on Metrics > Overview tab** — analyzes patterns ACROSS traces: health verdict, top issues, highest-leverage fix with code snippet, what's working, next steps. `POST /explain/project-metrics`. Cached 10m.
- **AI Correlation Analysis on Metrics > Correlation tab** — interprets the Pearson matrix in plain English: expected patterns, concerning patterns with likely cause and investigation step, key insight. `POST /explain/correlation`.
- **AI Prompt Regenerate** on Prompts > Merge with AI tab — accepts optional edge-case guidance and re-runs the merge with that as an extra rule. Adds `extra_instructions` field to `MergeRequest` with backend support.

### Added — Excel-style trace filters
- New `ColumnHeader` component renders into `document.body` via React Portal so popovers escape any parent `overflow:hidden` clipping.
- Filter columns: Trace ID, Pipeline, User, Status, Spans (multi-select with search, Select All ↔ Unselect All toggle, `__NONE__` sentinel for hide-all state).
- Sort columns: Latency (asc/desc), Time (asc/desc + From/To date range).
- Active-filter chips above the table with one-click clear.
- "Clear all" link resets every filter and sort.
- 200-trace fetch with all filtering/sorting client-side for instant UX.

### Added — Budget ↔ Alert channel mapping
- `BudgetRecord` gains 3 columns (auto-migrated): `alert_channel_ids` (JSON list of channel IDs), `last_fired_threshold` (de-dup state), `last_fired_at` (period boundary detection).
- `check_budget_alerts()` now uses explicit per-budget channel routing with falling-back to legacy trigger-name matching for old channels.
- **De-dup logic**: a budget at 84% won't spam every trace — only fires when crossing to a NEW higher threshold. State resets at period rollover.
- **Cascade delete**: deleting an alert channel automatically removes its ID from any budget that referenced it. Frontend confirm dialog lists the affected budgets by name first.
- `POST /budgets/{id}/test-fire` sends synthetic alerts to all mapped channels (kept in v0.6.0, moved to alerts page in later commit).
- `GET /alerts/channels/{id}/budgets` reverse lookup for the "Subscribed by N budgets" badge on alert channel cards.
- Budget edit form now has a multi-select channel picker.
- Budget cards show "Notifies:" chips with channel name + type icon, or a yellow warning when no channels are mapped.

### Added — Alerts page redesign
- Moved from PROJECT section to GLOBAL section in the sidebar.
- Subtitle: "Globally-shared webhook and Slack channels".
- "Project" free-text field replaced with **"Listens to project" dropdown** populated from `/traces/projects` (with "All projects" as default).
- Channel Name field has clearer label and helper text explaining it's a display label only — webhook URLs determine actual delivery.
- Trigger Events checkboxes no longer show `budget_50/80/100` — those are now configured per-budget. Backend `TRIGGER_TYPES` updated to match.
- Channel cards now show a "Subscribed by:" strip listing budgets and an inline "📢 N budgets" header badge.

### Added — Period-aware budget cards
- Budget cards show period-specific labels: "Spent today (resets at midnight)" / "this week (resets Monday)" / "this month (resets 1st)".
- Threshold pills now show 🔔 indicator if a threshold has been fired this period, with last-fired timestamp.
- Dashboard "Total Cost" card adds an italic "lifetime" hint so it's not confused with windowed budget spend.

### Added — Trace logging robustness
- SDK trace POST failures now log at `WARNING` level (was `DEBUG` which was silenced) so users see the real reason traces don't appear.
- Backend has a global exception handler that returns the actual error type + message in 500 responses instead of "Internal Server Error".

### Added — Auto-migration
- `_add_missing_columns()` in `database.py` walks each ORM model and runs `ALTER TABLE ADD COLUMN` for any missing columns. Idempotent, additive.
- Used to add: `traces.session_id`, `traces.prompt_versions_used`, `budgets.*`, `eval_jobs` (new table), `embedder_configs` (new table).

### Added — Project auto-creation from SDK
- `obtrac_config(project=...)` now POSTs to `/traces/projects` on init so the project shows in the dashboard immediately, before the first trace is logged. Idempotent, 2s timeout, silent fail.

### Added — Analytics period filter
- Top-right toggle on Analytics: Today / This Week / This Month / Lifetime.
- `/api/v1/analytics/tokens` and `/analytics/cost/over-time` accept a `period` query param (`daily | weekly | monthly | lifetime`, default `lifetime`).
- Backend filters traces by `created_at >= computed period_start`.
- Empty state shows the toggle so users can switch back to a wider window.
- Subtitle now shows "N traces · This Week · since <timestamp>".

### Removed
- **Test Fire button** removed from budget cards. Channel verification now happens entirely on the Alerts page where it belongs — alert channels test their delivery, budgets only configure routing. (The `POST /budgets/{id}/test-fire` backend endpoint is intentionally kept; it's just no longer exposed in the UI.)

---

## [v0.4.1-stable] — Original known-good baseline

**Tag:** `v0.4.1-stable`
**Commit:** `ce4c011`
**Install:** `pip install "obtrac[all] @ git+https://github.com/satyamk9git/ObTrac.git@v0.4.1-stable"`

This is the long-term stable rollback target. Use this tag for CI pinning, regression testing, or recovery from any v0.6.x issue.

### Features at this version
- Python SDK with `@trace` and `@observe` decorators
- FastAPI backend with trace storage, RAGAS evaluation, prompt registry, LLM config
- Next.js dashboard with single-list sidebar
- Multi-LLM evaluation as a synchronous endpoint (page hangs during eval)
- Per-trace metric explainer with AI diagnosis
- Cost budgets with implicit trigger-name routing to alert channels
- Slack and webhook alert channels
- Sessions, Compare, SQL Editor, Resources (datasets), Analytics
- LangChain, LangGraph, Google ADK example apps in `test_app/`
- Auto-create projects via API (no SDK auto-create)

### Known limitations versus v0.6.1
- No async eval (the dashboard blocks during long evaluations)
- No project-level or correlation-level AI insights
- No prompt-merge regenerate-with-guidance
- No Excel-style filters on the Traces page (only a Status dropdown)
- No explicit budget→alert channel mapping (uses trigger-name matching)
- No de-dup state on budget alerts (can spam if many traces land while above threshold)
- No embedder config (semantic GT matching uses hardcoded local MiniLM)
- No period filter on Analytics
- Single flat sidebar (Projects, Dashboard, Traces, etc. all mixed together)
- Backend trace POST failures log at DEBUG level (silently swallowed)

---

## How to install a specific version

Replace `<TAG>` with `v0.6.2`, `v0.6.1`, or `v0.4.1-stable`:

```bash
# First install
pip install "obtrac[all] @ git+https://github.com/satyamk9git/ObTrac.git@<TAG>"
python -m obtrac_sdk.cli install
python -m obtrac_sdk.cli start

# Upgrade an existing install
python -m obtrac_sdk.cli stop
pip install --upgrade --force-reinstall "obtrac[all] @ git+https://github.com/satyamk9git/ObTrac.git@<TAG>"
python -m obtrac_sdk.cli install
python -m obtrac_sdk.cli start
```

Your SQLite database, `.env`, and frontend build are preserved across version switches. Auto-migration handles any new schema columns on the next backend startup.

---

## Tags at a glance

| Tag | Use | Codebase |
|---|---|---|
| `v0.6.2` | Latest — install on new machines for the latest docs + features | Same as v0.6.1, docs updated |
| `v0.6.1` | All v0.6 features, the moment we cut the release tag | Same code as v0.6.0, version-bumped |
| `v0.4.1-stable` | Long-term rollback baseline | Pre-v0.6 features only |
