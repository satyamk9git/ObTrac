# ObTrac

**Open-source RAG observability and evaluation platform.** Trace your pipeline, run RAGAS evaluations, version your prompts, set budgets, and get AI-powered diagnoses of what's going wrong — all self-hosted, no SaaS, no telemetry.

```
┌─────────────────────────────────────────────────┐
│  ObTrac                          [Search] 🔔    │
├─────────────────────────────────────────────────┤
│ GLOBAL                                          │
│  🏠 Projects                                    │
│  📝 Prompts                                     │
│  🤖 LLM Config                                  │
│  🧠 Embedder Config                             │
│  🗄️  DB Config                                   │
│  📊 Resources                                   │
│  💻 SQL Editor                                  │
│  🔔 Alerts                                      │
├─────────────────────────────────────────────────┤
│ PROJECT: langgraph-agent                        │
│  📈 Dashboard                                   │
│  🔎 Traces                                      │
│  📐 Metrics                                     │
│  📊 Analytics                                   │
│  ⚖️  Compare                                    │
│  💬 Sessions                                    │
│  💰 Budgets                                     │
└─────────────────────────────────────────────────┘
```

| Latest stable | Long-term stable |
|---|---|
| **v0.6.4** — sidebar restructure, embedder config, async eval, AI insights, Excel filters, budget→alert mapping, Mustache-style `{{var}}` prompts | **v0.4.1-stable** — original known-good baseline |

---

## Table of Contents

1. [What's in v0.6.1](#whats-in-v061)
2. [Quick Install](#quick-install)
3. [Two install paths — latest vs stable](#two-install-paths--latest-vs-stable)
4. [Prerequisites](#prerequisites)
5. [Your First Traced App](#your-first-traced-app)
6. [Architecture](#architecture)
7. [Feature Tour](#feature-tour)
8. [SDK Reference](#sdk-reference)
9. [Configuration](#configuration)
10. [CLI Reference](#cli-reference)
11. [Upgrading and Rollback](#upgrading-and-rollback)
12. [Troubleshooting](#troubleshooting)
13. [FAQ](#faq)

---

## What's in v0.6.1

ObTrac is **3 things in one**:

1. **Python SDK** — Add `@trace` and `@observe` decorators to any function. Token counts, costs, latency, prompt versions, and span trees are captured automatically.
2. **FastAPI backend** — Stores traces, runs RAGAS evaluation as background jobs, manages global prompts/LLMs/embedders/budgets/alerts, exposes 30+ REST endpoints.
3. **Next.js dashboard** — Modern UI with Excel-style filters, AI-powered diagnoses, real-time eval status badges, and a global ↔ project navigation split.

### Major v0.6 features (versus v0.4.1)

| Area | What's new |
|---|---|
| **Navigation** | GLOBAL ↔ PROJECT sidebar split. Global tools (Prompts, LLM Config, Embedder, DB Config, Resources, SQL Editor, Alerts) live in the top section. Project pages (Dashboard, Traces, Metrics, Analytics, Compare, Sessions, Budgets) move to the bottom and only activate after picking a project. |
| **Embedder Config** | Globally-configured embedding model used by semantic ground-truth matching and retrieval helpers. Supports 7 providers: sentence-transformers, OpenAI, Azure OpenAI, Cohere, Vertex, HuggingFace, Ollama. CLI helper: `obtrac embedder list/add/test`. |
| **Async eval** | Multi-LLM RAGAS evaluation runs in a background daemon thread. The eval kicks off in <100ms and survives page navigation. A "running evals" badge in the top bar polls every 5s and lets you click into in-flight jobs. |
| **AI Metric Explainer** | Click any metric on a trace → modal shows the verdict, what the metric measures, AI diagnosis of *that specific trace*, and concrete improvement techniques. |
| **AI Project Insights** | New card on Metrics > Overview tab. Click "Generate Analysis" → LLM analyzes patterns ACROSS traces (not just one), returns a health verdict, top issues with root causes, and the highest-leverage fix with a code snippet. Cached 10 min. |
| **AI Correlation Analysis** | New card on Metrics > Correlation tab. AI interprets the Pearson matrix in plain English: expected patterns, concerning anti-correlations with likely causes, and what to investigate next. |
| **AI Prompt Regenerate** | On the prompt merge tab, an optional "extra guidance" textarea lets you regenerate the merged draft with edge cases the AI should respect. |
| **Excel-style trace filters** | Trace ID, Pipeline, User, Status, Spans columns filter via per-header popover (multi-select with search, Select All ↔ Unselect All toggle). Latency and Time columns sort. Time also filters by date range. Active filter chips above the table with one-click clear. |
| **Budget ↔ Alert channel mapping** | Each budget now has an explicit list of alert channels it routes to. De-dup state prevents the same threshold from firing twice in one period. Channels are global; mapping is per-budget. |
| **Period filter on Analytics** | Toggle: Today / This Week / This Month / Lifetime. All charts and stats re-render to the selected window. |
| **Auto-create project** | `obtrac_config(project="foo")` now POSTs to the backend on init so the project shows in the dashboard immediately, before the first trace logs. |
| **Logo + favicon** | Replace the placeholder gradient block with `frontend/public/obtrac_logo.png`. Set as favicon via Next's `app/icon.png` convention. |
| **Auto-migration** | New ORM columns (e.g. `budgets.alert_channel_ids`, `budgets.last_fired_threshold`) get added to existing SQLite databases on backend startup with `_add_missing_columns()`. Idempotent and additive — never drops or renames. |
| **Better error visibility** | SDK trace POST failures now log at WARNING (was DEBUG and silently swallowed). Backend has a global exception handler that returns the actual error type + message in 500 responses instead of generic "Internal Server Error". |
| **Project auto-create** | `obtrac_config(project="X")` calls `POST /traces/projects` so empty projects appear in the dashboard immediately. Idempotent, 2s timeout, silent fail. |

---

## Quick Install

### Latest stable (v0.6.1) — recommended

```bash
pip install "obtrac[all] @ git+https://github.com/satyamk9git/ObTrac.git@v0.6.4"
python -m obtrac_sdk.cli install
python -m obtrac_sdk.cli start
python -m obtrac_sdk.cli open
```

That's it. Three commands and you have a backend on `:8100`, a dashboard on `:3100`, and a browser open at the home page.

### Long-term stable (v0.4.1-stable) — for production-frozen environments

```bash
pip install "obtrac[all] @ git+https://github.com/satyamk9git/ObTrac.git@v0.4.1-stable"
python -m obtrac_sdk.cli install
python -m obtrac_sdk.cli start
```

---

## Two install paths — latest vs stable

ObTrac maintains **two named tags** for installation. They're independent and you can run them on different machines side-by-side.

| Tag | Install command | When to use |
|---|---|---|
| **`v0.6.1`** | `pip install "obtrac[all] @ git+https://github.com/satyamk9git/ObTrac.git@v0.6.4"` | All the latest features. Recommended for new installs and dev environments. |
| **`v0.4.1-stable`** | `pip install "obtrac[all] @ git+https://github.com/satyamk9git/ObTrac.git@v0.4.1-stable"` | Original known-good baseline. Use this when you need a frozen pre-v0.6 version (e.g., CI pinning, regression testing, or rollback after a v0.6.x issue). |

**The `@<tag>` part is critical.** Without it, pip pulls whatever's on the default branch. With it, pip pulls *exactly* that immutable named commit.

You can also pin to **any commit hash** the same way:
```bash
pip install "obtrac[all] @ git+https://github.com/satyamk9git/ObTrac.git@<7-char-hash>"
```

---

## Prerequisites

| Tool | Version | Why |
|---|---|---|
| **Python** | 3.10+ | SDK + backend |
| **Node.js** | 18+ | Frontend (Next.js) |
| **Git** | latest | Used by `obtrac install` to clone the project files |
| **An LLM provider** | — | Azure OpenAI, OpenAI, Anthropic, Gemini, Bedrock, Ollama, etc. (configured via the dashboard's LLM Config page) |

Verify:
```bash
python --version    # 3.10+
node --version      # 18+
git --version
```

If any of those fail, install from the respective official site first.

---

## Your First Traced App

After running the install commands, the dashboard is empty. Let's log a real trace.

Create `my_app.py`:

```python
from obtrac_sdk import obtrac_config, observe, trace

# Auto-creates the project on the backend so it shows up immediately
obtrac_config(
    project="my-first-project",
    backend_url="http://localhost:8100",
    user="satyam",
)

@trace(name="retrieve", span_type="retrieval")
def retrieve(query):
    # Replace with your real retriever
    return [f"Doc 1 about {query}", f"Doc 2 about {query}"]

@trace(
    name="generate",
    span_type="generation",
    model="gpt-4o",
    cost={"input_token_cost": 0.0025, "output_token_cost": 0.01},
)
def generate(query, context):
    return f"Based on {len(context)} docs, here's an answer to: {query}"

@observe(name="rag_pipeline")
def pipeline(query):
    docs = retrieve(query)
    return generate(query, docs)

if __name__ == "__main__":
    print(pipeline("What is RAG?"))
    print("Open http://localhost:3100 to see the trace.")
```

Run it:
```bash
python my_app.py
```

Then open the dashboard:
1. **Projects** in the global sidebar → click `my-first-project`
2. **Traces** in the project sidebar → click your trace
3. See the span tree, token counts, latency, cost, and (after configuring an LLM) RAGAS metrics

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  YOUR APPS                                                       │
│  LangChain · LangGraph · LlamaIndex · Custom RAG · Google ADK    │
└────────────────────────────┬─────────────────────────────────────┘
                             ↓
┌──────────────────────────────────────────────────────────────────┐
│  obtrac_sdk                                                      │
│  @observe / @trace decorators · get_prompt() registry client     │
└────────────────────────────┬─────────────────────────────────────┘
                             ↓ HTTP POST /api/v1/traces
┌──────────────────────────────────────────────────────────────────┐
│  FASTAPI BACKEND  (port 8100)                                    │
│  Tracing · RAGAS Eval · Prompt Registry · LiteLLM Gateway        │
│  Embedder Service · Cost Engine · Alerts · SQL Editor · AI       │
│  Insights · Auto-Migration                                       │
│                                                                  │
│  SQLite (default, ~/.obtrac/backend/data/obtrac.db)              │
│  PostgreSQL (planned in v0.7 — DB Config UI is a placeholder)    │
└────────────────────────────┬─────────────────────────────────────┘
                             ↓ JSON API
┌──────────────────────────────────────────────────────────────────┐
│  NEXT.JS DASHBOARD  (port 3100)                                  │
│  GLOBAL: Projects · Prompts · LLM/Embedder/DB Config · Resources │
│          · SQL Editor · Alerts                                   │
│  PROJECT: Dashboard · Traces · Metrics · Analytics · Compare ·   │
│           Sessions · Budgets                                     │
└──────────────────────────────────────────────────────────────────┘
```

---

## Feature Tour

### Trace explorer with Excel-style filters

Every column header on the **Traces** page is a clickable popover:

- **Trace ID** — multi-select with search
- **Pipeline** — multi-select pipeline names
- **User** — multi-select users
- **Status** — success / error
- **Spans** — exact span count
- **Latency** — sort ascending / descending
- **Time** — sort + From/To date range picker

Active filter chips above the table show what's selected. Click any chip to clear that one filter, or "Clear all" to reset everything.

### Multi-LLM evaluation, async by default

1. Open any trace
2. **Run RAGAS Evaluation** → pick LLMs + metrics → click **Evaluate**
3. The eval queues **immediately**. You can navigate away or close the browser — the daemon thread keeps running.
4. The top-right **"X evals running"** badge polls every 5s and lets you click into in-flight jobs.
5. When the trace detail page reloads, it auto-detects in-flight jobs and resumes the spinner.

### AI-powered diagnosis at three levels

| Level | Where | What it analyzes |
|---|---|---|
| **Per-trace** | Click any metric score on a trace → Metric Explainer modal | This specific trace: diagnosis, evidence quote, fix, priority |
| **Per-project** | Metrics > Overview → "Generate Analysis" | Patterns ACROSS all traces in a project: health verdict, top issues, highest-leverage fix with code snippet |
| **Per-correlation** | Metrics > Correlation → "Analyze Metrics" | The Pearson matrix in plain English: expected vs concerning patterns, root causes, what to check |

All cached for 10 minutes per project to avoid burning tokens on refresh.

### Versioned global prompt registry

- Prompts are **global** — accessible from any project
- Every change creates a new version with a commit message
- "Active" version is the one your code fetches via `get_prompt(name)`
- **AI prompt merging** — pick 2+ versions, the LLM combines the best of each, optional "edge case guidance" textarea
- Every trace records which prompt name + version it used (audit trail)

### Cost budgets with explicit alert routing

Budgets and alert channels are now **wired explicitly**:

1. Create an alert channel in **Alerts** (Slack webhook or generic webhook)
2. Open **Budgets** → Edit a budget → check the channel(s) it should notify
3. When a trace pushes spend across a threshold (50%, 80%, 100%), only the mapped channels fire
4. **De-dup state** prevents spam: a budget at 84% won't fire on every new trace, only when crossing to a NEW threshold (50→80→100)
5. State resets at the period boundary (daily at midnight, weekly Monday, monthly 1st)

### Embedder Config — bring your own embedding model

Used by semantic ground-truth matching and retrieval helpers. Mirrors LLM Config:

- Add multiple configs, mark one as **default**
- Test button verifies it actually works (encodes "test sentence" → returns dimensions)
- 7 providers supported, fallback to local MiniLM if nothing's configured

### Period-aware Analytics

Top-right toggle: **Today / This Week / This Month / Lifetime**. All charts and stats filter to the selected window. Empty state correctly distinguishes "no traces in this window" from "no traces at all."

---

## SDK Reference

### `obtrac_config()`

```python
from obtrac_sdk import obtrac_config

obtrac_config(
    project="my-app",                           # required — project name
    backend_url="http://localhost:8100",        # default
    user="satyam",                              # optional
    session_id="chat_abc123",                   # optional, groups multi-turn
    auto_eval=False,                            # if True, runs RAGAS on every trace
    default_metrics=["faithfulness", "answer_relevancy"],
    cost={                                      # default cost rates if @trace doesn't override
        "input_token_cost": 0.0025,
        "output_token_cost": 0.01,
    },
    auto_create_project=True,                   # default — POSTs to /traces/projects on init
)
```

### `@trace` — instrument a single function

```python
from obtrac_sdk import trace

@trace(
    name="retrieve",                             # span name
    span_type="retrieval",                       # retrieval | generation | tool_call | agent | embedding | custom
    model="text-embedding-3-small",              # optional model name (auto-captures cost from LiteLLM if available)
    cost={                                       # per-span override
        "input_token_cost": 0.00002,
        "output_token_cost": 0,
    },
    query="user_question",                       # map function arg name → query
    context="ctx",                               # map function arg name → context
    response="return",                           # "return" = use return value as response
)
def retrieve(user_question, ctx):
    return vectorstore.search(user_question)
```

### `@observe` — wrap the entire pipeline

```python
from obtrac_sdk import observe

@observe(
    name="rag_pipeline",
    metrics=["faithfulness", "answer_relevancy"],   # auto-eval metrics (requires auto_eval=True)
    query="question",
    context="docs",
    answer="return",
    ground_truth="expected",
)
def pipeline(question, docs=None, expected=None):
    docs = retrieve(question)
    return generate(question, docs)
```

### `get_prompt()` — fetch a versioned prompt

```python
from obtrac_sdk import get_prompt

# Latest active version
prompt = get_prompt("rag_answer")
text = prompt.render(question="What is RAG?", context="...")

# Pin to a specific version
prompt = get_prompt("rag_answer", version=2)
text = prompt.render(question="...", context="...")
```

`render()` automatically stamps the prompt name + version onto the current trace, so you have an audit trail of which prompt produced each answer.

### `log_llm_usage()` — manual override

```python
from obtrac_sdk import log_llm_usage, trace

@trace(name="generate")
def generate(query):
    response = llm.call(query)
    log_llm_usage(
        tokens={"prompt": 500, "completion": 100},
        cost=0.0075,
        model="gpt-4o",
    )
    return response
```

---

## Configuration

### LLM credentials

Two ways to provide them:

**Option A — `.env` file** (recommended for first-time setup)

ObTrac auto-clones the project to `~/.obtrac/`. Create the file there:

```bash
# ~/.obtrac/.env
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_MODEL_NAME=gpt-4o
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_API_KEY=your-api-key-here
AZURE_OPENAI_API_VERSION=2024-12-01-preview
```

**Option B — Dashboard UI** (recommended for adding multiple LLMs)

Open http://localhost:3100 → **LLM Config** in the global sidebar → **+ Add LLM** → fill in the form → check **"Use for Auto-Evaluation"** if you want this LLM to run RAGAS scoring.

### Embedder

For semantic ground-truth matching to work optimally, configure an embedder:

1. Open **Embedder Config** in the global sidebar
2. **+ New Embedder** → pick a provider, enter API key (if needed), set as default
3. Click **Test** to verify

If you skip this, ObTrac falls back to a local `sentence-transformers/all-MiniLM-L6-v2` model that downloads automatically on first use.

---

## CLI Reference

The `obtrac` command (or `python -m obtrac_sdk.cli` if it's not on your PATH):

| Command | What it does |
|---|---|
| `obtrac install` | One-time: clone project files to `~/.obtrac`, install frontend deps, build the dashboard. Idempotent — also runs on every upgrade to refresh the build. |
| `obtrac start` | Start backend (port 8100) + frontend (port 3100) in the background |
| `obtrac stop` | Stop both services |
| `obtrac status` | Print which services are currently running |
| `obtrac open` | Open the dashboard in your default browser |
| `obtrac embedder list` | List all configured embedders |
| `obtrac embedder add --name X --provider Y --model Z [--default]` | Create a new embedder config |
| `obtrac embedder test <name>` | Verify an embedder works (encodes a test string) |
| `obtrac embedder set-default <name>` | Mark as default |
| `obtrac embedder delete <name>` | Remove an embedder |

If `obtrac` is not found on PATH after install, use `python -m obtrac_sdk.cli ...` — it always works.

---

## Upgrading and Rollback

### Upgrade an existing install

```bash
python -m obtrac_sdk.cli stop
pip install --upgrade --force-reinstall "obtrac[all] @ git+https://github.com/satyamk9git/ObTrac.git@v0.6.4"
python -m obtrac_sdk.cli install
python -m obtrac_sdk.cli start
```

`--force-reinstall` is needed because pip caches git installs by version string. Without it, switching between tags can be a no-op.

### Roll back to v0.4.1-stable

```bash
python -m obtrac_sdk.cli stop
pip install --upgrade --force-reinstall "obtrac[all] @ git+https://github.com/satyamk9git/ObTrac.git@v0.4.1-stable"
python -m obtrac_sdk.cli install
python -m obtrac_sdk.cli start
```

### Data preservation across versions

- **Your SQLite database is never touched** by upgrades or rollbacks. Traces, prompts, budgets, alert channels — everything stays at `~/.obtrac/backend/data/obtrac.db`.
- **Schema migrations are additive only.** v0.6 adds new columns; v0.4 simply ignores them.
- **Your `.env` file is preserved.** It lives outside the cloned repo (`~/.obtrac/.env`) and never gets touched by `git reset`.

### Verify which version is installed

```bash
python -c "import obtrac_sdk; print(obtrac_sdk.__version__)"
```

The dashboard sidebar footer also shows the version (`v0.4.1` or `v0.6.1`).

---

## Troubleshooting

### `obtrac: command not found`

PATH issue. Use the module form:
```bash
python -m obtrac_sdk.cli start
```

Or add Python's Scripts folder to PATH:
```bash
python -c "import sys, os; print(os.path.join(sys.prefix, 'Scripts'))"
```

### Backend won't start — port already in use

```bash
# Windows
netstat -ano | findstr :8100
taskkill /PID <pid> /F

# Linux/Mac
lsof -i :8100
kill -9 <pid>
```

Or just `obtrac stop` first.

### Frontend stuck on a stale page after upgrade

`obtrac install` rebuilds the frontend, but browsers cache aggressively. Hard-reload with `Ctrl+Shift+R` (`Cmd+Shift+R` on Mac).

### Trace API returns 500

After commit `176fb90` we have a global exception handler that returns the actual error in 500 responses. Check the body:

```bash
curl -X POST http://localhost:8100/api/v1/traces -H "Content-Type: application/json" -d '{}' | python -m json.tool
```

Look for `"error"` and `"message"` fields. The most common cause is an old SQLite missing a new column — but the auto-migration on backend startup should fix that. If it persists, check the backend log for `Schema migration: ...` lines.

### Auto-eval shows "failed" or "partial"

Two common causes:

1. **No LLM marked for auto-eval.** Open **LLM Config** in the dashboard, edit your judge LLM, check **"Use for Auto-Evaluation"**, save.
2. **RAGAS quirk on certain Azure deployments.** Try `answer_relevancy` first — it's the most reliable. `faithfulness` and `context_precision` sometimes return NaN on specific deployments. We have a `_extract_score` helper that converts NaN to None.

### Slack alerts going to the wrong channel

Slack incoming webhook URLs are bound to **one specific channel** at the moment they're created. The "Channel Name" you type in ObTrac is just a display label — it does not influence routing. If you want to post to a different Slack channel, you have to generate a new webhook URL from `https://api.slack.com/apps` → your app → Incoming Webhooks → **Add New Webhook to Workspace** → pick the right channel.

### My budget is at 90% but I never got the alert

Three things to check:
1. Budget has at least one **alert channel** mapped (Edit budget → check channels → save)
2. Budget's `last_fired_threshold` isn't already set to a higher value (de-dup logic — once it fires at 80%, it won't fire again at 81-99%)
3. Real traces have actually landed on the backend after the mapping was set up (the de-dup check only runs during trace ingestion)

To force-test the wiring without waiting for real traces, use the **Send Test** button on the alert channel card in the Alerts page.

---

## FAQ

**Q: Can I use OpenAI directly instead of Azure?**
Yes. In the LLM Config page, pick `OpenAI` as the provider and paste your `sk-...` key.

**Q: Does it work with local LLMs (Ollama)?**
Yes. Both LLM Config and Embedder Config support Ollama. Set `api_base` to `http://localhost:11434`.

**Q: How much does it cost to run ObTrac itself?**
Zero. ObTrac is MIT-licensed open source. You only pay for whatever LLM API calls you make.

**Q: Can I use it in production?**
Yes for SQLite-scale workloads (a few thousand traces a day). For higher volume or shared deployments, you'll want Postgres — that's coming in v0.7 (DB Config). The current placeholder page describes the planned flow.

**Q: Where are traces stored?**
SQLite at `~/.obtrac/backend/data/obtrac.db`. Single file, easy to back up — just copy it.

**Q: How do I export traces?**
Open **Metrics** in any project → **Export CSV** or **Export JSON** in the top-right.

**Q: What's the difference between `@trace` and `@observe`?**
`@trace` creates a single span (one step in a pipeline). `@observe` creates a root trace (the whole pipeline) — any `@trace` calls inside an `@observe`-wrapped function become children in the span tree.

**Q: Does it support async functions?**
Yes. Both `@trace` and `@observe` detect async functions and work with `await`.

**Q: How do I track multi-turn conversations?**
Pass `session_id` to `obtrac_config()`. All traces with the same session_id appear in the **Sessions** page grouped as a conversation.

**Q: Are there any user-facing breaking changes between v0.4.1 and v0.6.1?**
None at the SDK level. All decorators, configs, and prompts behave identically. The only change you'd notice is that the dashboard sidebar layout is different (GLOBAL ↔ PROJECT split) and some pages moved between sections.

**Q: How do I report a bug or suggest a feature?**
Open an issue at https://github.com/satyamk9git/ObTrac/issues

---

See [docs/setup_new_machine.md](docs/setup_new_machine.md) for the new-machine onboarding flow and [docs/examples.md](docs/examples.md) for code recipes covering RAG, agents, LangChain, LangGraph, Google ADK, and edge cases.
