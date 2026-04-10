# ObTrac

**Open-source RAG observability and evaluation framework. Trace, evaluate, and debug your AI pipelines without writing boilerplate.**

ObTrac gives you a plug-and-play SDK and a beautiful dashboard to monitor your RAG and Agent applications. Built for any LLM (Azure OpenAI, OpenAI, Anthropic, Gemini, Ollama, etc.) and any framework (LangChain, LangGraph, Google ADK, custom).

---

## Table of Contents

1. [What is ObTrac?](#what-is-obtrac)
2. [Quick Demo](#quick-demo)
3. [Prerequisites](#prerequisites)
4. [Installation (Step by Step)](#installation-step-by-step)
5. [Setup Azure OpenAI Credentials](#setup-azure-openai-credentials)
6. [Running ObTrac](#running-obtrac)
7. [Your First Traced App](#your-first-traced-app)
8. [Using @trace and @observe](#using-trace-and-observe)
9. [The Dashboard](#the-dashboard)
10. [Migrating to Another System](#migrating-to-another-system)
11. [Troubleshooting](#troubleshooting)
12. [FAQ](#faq)

---

## What is ObTrac?

ObTrac is **3 things in one**:

1. **Python SDK** — Add `@trace` and `@observe` decorators to your code. ObTrac captures every input, output, token, cost, and latency automatically.
2. **Backend (FastAPI)** — Stores traces, runs RAGAS evaluation, manages LLM configs.
3. **Frontend Dashboard (Next.js)** — Beautiful UI to view traces, metrics, costs, and run evaluations.

### Why use it?

- **Zero boilerplate** — Just add decorators. No SDK initialization mess.
- **Auto token + cost tracking** — Uses tiktoken or LiteLLM response data.
- **Multi-LLM judge** — Compare your RAG pipeline scored by multiple judges.
- **Session tracking** — Group multi-turn conversations.
- **Annotations** — Thumbs up/down + notes for human feedback.
- **SQL editor** — Query your trace data directly in the browser.
- **Framework agnostic** — Works with LangChain, LangGraph, ADK, custom.

---

## Quick Demo

After installation, you'll have:

| URL | What |
|---|---|
| http://localhost:3100 | **Dashboard** (Next.js frontend) |
| http://localhost:8100/docs | **API docs** (FastAPI Swagger) |
| http://localhost:8501 | RAG test app (Streamlit) |
| http://localhost:8502 | Multi-Agent test app |
| http://localhost:8503 | LangChain example |
| http://localhost:8504 | LangGraph example |
| http://localhost:8505 | Google ADK example |

---

## Prerequisites

You need:

- **Python 3.10 or higher** — [Download here](https://www.python.org/downloads/)
- **Node.js 18 or higher** — [Download here](https://nodejs.org/)
- **An Azure OpenAI account** (or any other LLM provider)
- **A terminal** — PowerShell, Bash, Command Prompt, etc.

### Check if you have them installed

Open a terminal and run:

```bash
python --version    # Should show Python 3.10 or higher
node --version      # Should show v18 or higher
npm --version       # Should show 9 or higher
```

If any of these fail, install them from the links above first.

---

## Installation (Step by Step)

### Step 1: Clone or download the project

```bash
git clone <your-repo-url> ObTrac
cd ObTrac
```

Or just copy the entire `ObTrac` folder to your machine.

### Step 2: Install the SDK as an editable Python package

This makes `obtrac_sdk` available everywhere on your machine.

```bash
pip install -e .
```

What this does: installs `obtrac_sdk` from `pyproject.toml` so any Python script can `from obtrac_sdk import trace, observe`.

### Step 3: Install backend dependencies

```bash
cd backend
pip install -r requirements.txt
cd ..
```

This installs FastAPI, SQLAlchemy, RAGAS, LiteLLM, etc.

### Step 4: Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

This installs Next.js, React, Recharts, Tailwind.

### Step 5: Install test app dependencies (optional but recommended)

```bash
pip install -r test_app/requirements.txt
```

### Step 6: Verify installation

```bash
python -c "from obtrac_sdk import obtrac_config, trace, observe; print('SDK OK')"
```

If you see `SDK OK`, you're good.

---

## Setup Azure OpenAI Credentials

ObTrac supports many providers, but Azure OpenAI is the most common.

### Step 1: Create a `.env` file

In the project root (`ObTrac/`), create a file called `.env`:

```bash
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_MODEL_NAME=gpt-4o
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_API_KEY=your-api-key-here
AZURE_OPENAI_API_VERSION=2024-12-01-preview
```

Replace the values with your actual Azure OpenAI credentials. Don't share this file or commit it to git.

### Step 2: Test the credentials

```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
import os
print('Endpoint:', os.getenv('AZURE_OPENAI_ENDPOINT'))
print('Key length:', len(os.getenv('AZURE_OPENAI_API_KEY', '')))
"
```

---

## Running ObTrac

You'll run **3 things in parallel**: Backend, Frontend, and one of the test apps.

### Terminal 1: Start the Backend

```bash
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8100
```

Wait until you see:
```
ObTrac backend started successfully
```

Open http://localhost:8100/docs to see the API.

### Terminal 2: Start the Frontend

```bash
cd frontend
npm run build       # Build for production (faster)
npm start -- --port 3100
```

Or for development with hot-reload (slower):
```bash
cd frontend
npx next dev --port 3100
```

Wait for `Ready in X.Xs`. Open http://localhost:3100.

### Terminal 3: Start a Test App

Pick one:

```bash
# Simple RAG (FAISS + Azure OpenAI)
streamlit run test_app/app.py --server.port 8501

# Multi-agent (planner/executor/synthesizer/reviewer)
streamlit run test_app/agent_app.py --server.port 8502

# LangChain example
streamlit run test_app/langchain_app.py --server.port 8503

# LangGraph example
streamlit run test_app/langgraph_app.py --server.port 8504

# Google ADK example
streamlit run test_app/google_adk_app.py --server.port 8505
```

Open the corresponding URL (e.g., http://localhost:8501).

---

## Your First Traced App

Create a file called `my_app.py` in the project root:

```python
from obtrac_sdk import obtrac_config, trace, observe

# Step 1: Configure ObTrac (do this once at the top of your app)
config = obtrac_config(
    project="my-first-project",
    backend_url="http://localhost:8100",
    user="satyam",
)

# Step 2: Decorate functions with @trace
@trace(name="fetch_docs", span_type="retrieval")
def fetch_docs(query):
    return [f"Doc 1 about {query}", f"Doc 2 about {query}"]

@trace(name="generate_answer", span_type="generation",
       model="gpt-4o",
       cost={"input_token_cost": 0.0025, "output_token_cost": 0.01})
def generate_answer(query, docs):
    return f"Based on {len(docs)} docs, the answer is: {query} explained."

# Step 3: Use @observe for the full pipeline
@observe(name="my_rag_pipeline")
def pipeline(query):
    docs = fetch_docs(query)
    answer = generate_answer(query, docs)
    return answer

# Step 4: Run it
if __name__ == "__main__":
    answer = pipeline("What is RAG?")
    print(answer)
    print("Check your trace at http://localhost:3100")
```

Run it:

```bash
python my_app.py
```

Open http://localhost:3100 → click "my-first-project" → see your trace.

---

## Using @trace and @observe

### `@trace` — track individual function calls (one span)

```python
@trace(
    name="my_step",                         # Span name
    span_type="generation",                 # retrieval | generation | tool_call | agent | embedding | custom
    model="gpt-4o",                          # Model name (optional)
    cost={                                   # Per-span cost (optional, overrides global)
        "input_token_cost": 0.0025,
        "output_token_cost": 0.01,
    },
    query="user_question",                   # Map function arg name → query
    context="ctx",                           # Map function arg name → context
    response="return",                       # "return" = use return value as response
)
def my_step(user_question, ctx):
    return llm.call(user_question, ctx)
```

### `@observe` — wrap the entire pipeline

```python
@observe(
    name="rag_pipeline",                                 # Pipeline name
    metrics=["faithfulness", "answer_relevancy"],         # Auto-eval metrics (requires auto_eval=True)
    query="question",                                     # Map arg name → query
    context="docs",                                       # Map arg name → context (or auto from spans)
    answer="return",                                      # Default: return value
    ground_truth="expected",                              # Map arg name → ground truth
)
def pipeline(question, db, docs=None, expected=None):
    docs = retrieve(question)
    return generate(question, docs)
```

### Field Mapping — explicit vs auto

If your variable names are different from the standard (`query`, `context`, `answer`), you can either:

**Option A: Use standard names** (auto-detected)
```python
@observe(name="pipeline")
def pipeline(query, vectorstore):
    chunks = retrieve(query)
    return generate(query, chunks)  # return = answer
```

**Option B: Map explicitly**
```python
@observe(name="pipeline", query="q", answer="return")
def pipeline(q, db):
    return generate(q, db)
```

### Cost Calculation Priority

1. If `@trace(cost={...})` is set → use that
2. Else if `obtrac_config(cost={...})` is set → use global
3. Else → cost is $0

For different models per agent:
```python
@trace(name="planner", model="gpt-4o",
       cost={"input_token_cost": 0.0025, "output_token_cost": 0.01})
def planner(): ...

@trace(name="fast_search", model="gemini-flash",
       cost={"input_token_cost": 0.00015, "output_token_cost": 0.0006})
def search(): ...
```

### Token Tracking

Tokens are auto-counted using **tiktoken** based on inputs/outputs. If you use LiteLLM, the actual token counts from the response are used.

You can override manually:
```python
from obtrac_sdk import log_llm_usage

@trace(name="generate")
def generate(query):
    response = llm.call(query)
    log_llm_usage(
        tokens={"prompt": 500, "completion": 100},
        cost=0.0075,    # Optional override
        model="gpt-4o",
    )
    return response
```

---

## The Dashboard

http://localhost:3100

### Pages

| Page | What |
|---|---|
| **Home** (`/`) | All projects with stats — click to enter a project |
| **Dashboard** | Project overview: total traces, latency, cost, recent traces |
| **Traces** | Full list of traces with filters and search |
| **Trace Detail** | Span tree, prompts, metrics, evaluation, annotations |
| **Metrics** | RAGAS metrics tabs: Overview, Per-Query, Worst Traces, Correlation, By Model |
| **Analytics** | Token & cost charts, distribution, top consumers |
| **Compare** | Side-by-side trace diff (A vs B) |
| **Sessions** | Multi-turn conversations grouped by `session_id` |
| **LLM Config** | Manage LLM providers (Azure, OpenAI, Claude, Gemini, etc.) |
| **Resources** | Upload ground truth datasets (CSV/JSON) |
| **SQL Editor** | Query the SQLite database directly |

### Search

Press **Ctrl+K** anywhere to open the global search bar.

### Setting up Auto-Evaluation

1. Go to **LLM Config**
2. Click **+ Add LLM**
3. Fill in your Azure OpenAI credentials
4. Check **"Use for Auto-Evaluation"**
5. Save

Now any pipeline with `@observe(metrics=[...])` and `auto_eval=True` will automatically evaluate using that LLM.

---

## Migrating to Another System

### Option 1: Copy the SDK (simplest)

Just copy the `obtrac_sdk/` folder into your project:

```bash
your-project/
├── obtrac_sdk/        # Copy this folder here
├── my_app.py
└── ...
```

In your code:
```python
from obtrac_sdk import obtrac_config, trace, observe
```

The SDK only needs `requests` and `tiktoken` to work. Backend URL points to wherever you're hosting ObTrac.

### Option 2: Pip install (recommended)

On the new system:

```bash
git clone <your-obtrac-repo>
cd ObTrac
pip install -e .
```

Now any Python project on that machine can `from obtrac_sdk import ...`.

### Option 3: Build a wheel

```bash
cd ObTrac
pip install build
python -m build
```

This creates `dist/obtrac_sdk-0.1.0-py3-none-any.whl`. Copy the wheel to any machine and:

```bash
pip install obtrac_sdk-0.1.0-py3-none-any.whl
```

### Migrating the database

ObTrac uses SQLite at `backend/data/obtrac.db`. To migrate:

```bash
# On old system
cp backend/data/obtrac.db backup.db

# Copy backup.db to new system, then
cp backup.db ObTrac/backend/data/obtrac.db
```

For production, switch to PostgreSQL by editing `backend/app/db/database.py`:

```python
DATABASE_URL = "postgresql://user:pass@host:5432/obtrac"
```

---

## Troubleshooting

### Backend won't start

```bash
# Check what's on port 8100
netstat -ano | grep ":8100"

# Kill any process holding it
# Windows: taskkill /PID <pid> /F
# Linux/Mac: kill -9 <pid>
```

### Frontend shows "Trace not found"

The frontend is hitting the wrong API URL. Check `frontend/next.config.js` and the API URL in each page (`http://localhost:8100/api/v1`).

### `ImportError: cannot import name 'obtrac_config'`

Stale Python cache. Run:
```bash
find . -name __pycache__ -exec rm -rf {} +
```

Then restart your app.

### Auto-eval shows "failed" or "partial"

RAGAS 0.4.x has known issues with Azure OpenAI for some metrics. Workarounds:
- Use **manual evaluation** from the trace detail page (works reliably)
- Try `answer_relevancy` instead of `faithfulness`
- Make sure your `@observe` returns the **answer text**, not a dict

### Dashboard pages are slow

Run the frontend in **production mode** instead of dev:
```bash
cd frontend
npm run build
npm start -- --port 3100
```

Production is ~10-20x faster than dev.

### `eval_status: failed` everywhere

Check that you've enabled **"Use for Auto-Evaluation"** on at least one LLM config in the dashboard. Without it, auto-eval has no judge LLM.

### Streamlit `.env` not loading

Make sure `python-dotenv` is installed:
```bash
pip install python-dotenv
```

And `load_dotenv()` is called at the top of your Streamlit script.

---

## FAQ

**Q: Do I need MLflow?**
A: No. ObTrac has its own storage (SQLite). MLflow integration is optional.

**Q: Can I use OpenAI directly instead of Azure?**
A: Yes. Set `OPENAI_API_KEY` in `.env` and configure the LLM as `provider="openai"`.

**Q: Does it work with local LLMs (Ollama)?**
A: Yes. Use `provider="ollama"` and set `api_base="http://localhost:11434"`.

**Q: How much does it cost to run ObTrac?**
A: ObTrac itself is free (open source). You only pay for LLM API calls if you use a paid provider.

**Q: Can I use it in production?**
A: It's designed for it. Use PostgreSQL instead of SQLite, run with Gunicorn, and put the frontend behind nginx.

**Q: Does it support async?**
A: Yes. `@trace` automatically detects async functions and works with `await`.

**Q: Where are traces stored?**
A: SQLite database at `backend/data/obtrac.db`. You can query it via the SQL Editor in the dashboard.

**Q: Can I export traces?**
A: Yes. Go to **Metrics** → click **Export CSV** or **Export JSON**.

**Q: What's the difference between `@trace` and `@observe`?**
A: `@trace` creates a single span (one step). `@observe` creates a root trace (the full pipeline) and all `@trace` spans inside it become children.

**Q: How do I track multi-turn conversations?**
A: Set `session_id` in `obtrac_config()`. All traces with the same session_id appear in the **Sessions** page as a conversation.

---

See [EXAMPLES.md](EXAMPLES.md) for detailed code examples and edge cases.
