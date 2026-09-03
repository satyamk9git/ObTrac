# ObTrac × Google ADK — Integration Guide

Full tracing of Google ADK agents with ObTrac: every LLM call, every tool call,
every conversation turn — all visible in the ObTrac dashboard with zero changes
to your agent logic.

---

## Table of Contents

1. [What you get](#1-what-you-get)
2. [Prerequisites](#2-prerequisites)
3. [Install](#3-install)
4. [Project structure](#4-project-structure)
5. [Step 1 — Copy the callbacks module](#5-step-1--copy-the-callbacks-module)
6. [Step 2 — Configure ObTrac](#6-step-2--configure-obtrac)
7. [Step 3 — Wire callbacks into your Agent](#7-step-3--wire-callbacks-into-your-agent)
8. [Step 4 — Trace individual tools (optional)](#8-step-4--trace-individual-tools-optional)
9. [Step 5 — Run with adk web](#9-step-5--run-with-adk-web)
10. [What appears in the dashboard](#10-what-appears-in-the-dashboard)
11. [Session continuity (HITL / multi-turn)](#11-session-continuity-hitl--multi-turn)
12. [Using prompt registry](#12-using-prompt-registry)
13. [@trace on your own functions](#13-trace-on-your-own-functions)
14. [Full working example](#14-full-working-example)
15. [Troubleshooting](#15-troubleshooting)
16. [Reference — callback signatures](#16-reference--callback-signatures)

---

## 1. What you get

| Signal | How captured |
|---|---|
| Root Trace per turn | `before_agent_callback` / `after_agent_callback` |
| LLM call Span (generation) | `before_model_callback` / `after_model_callback` |
| Tool call Span | `before_tool_callback` / `after_tool_callback` |
| Token usage | Extracted from `LlmResponse.usage_metadata` |
| Query / Answer | Extracted from session events |
| Session ID (multi-turn) | Auto-detected from `callback_context.session.id` |
| Cost | Calculated from config token rates |

Everything flows into the ObTrac dashboard automatically — Traces, Sessions,
Analytics, and RAGAS evaluation — without touching your agent logic.

---

## 2. Prerequisites

- Python 3.10+
- ObTrac backend running (`uvicorn app.main:app --port 8100`)
- ObTrac frontend running (`npm run dev` on port 3100)
- Google ADK installed (`pip install google-adk`)
- An LLM provider (Azure OpenAI, OpenAI, Gemini, etc.)

---

## 3. Install

```bash
# Install ObTrac SDK (latest)
pip install "obtrac[all] @ git+https://github.com/satyamk9git/ObTrac.git@v0.6.8"

# Install Google ADK
pip install google-adk

# LiteLLM for provider abstraction (recommended)
pip install litellm
```

---

## 4. Project structure

ADK requires each agent to be a Python package (folder with `__init__.py`
that exports `root_agent`). ObTrac callbacks live in a shared `callbacks/`
package alongside your agent packages.

```
my_adk_project/
├── .env                        ← LLM API keys
├── callbacks/                  ← ObTrac hooks (copy once, reuse everywhere)
│   ├── __init__.py
│   └── obtrac_callback.py
├── my_agent/                   ← your ADK agent
│   ├── __init__.py             ← must export root_agent
│   └── agent.py
└── tools/                      ← optional: shared tool functions
    ├── __init__.py
    └── my_tools.py
```

Run from the project root:
```bash
cd my_adk_project
adk web .          # serves all agents in subdirectories
# OR
adk web my_agent   # serves one specific agent
```

---

## 5. Step 1 — Copy the callbacks module

Copy `demos/google_adk/callbacks/` from the ObTrac repo into your project root.
The key file is `callbacks/obtrac_callback.py`.

```
callbacks/
├── __init__.py
└── obtrac_callback.py
```

**`callbacks/__init__.py`** — exports all six hooks:
```python
from callbacks.obtrac_callback import (
    obtrac_before_agent,
    obtrac_after_agent,
    obtrac_before_model,
    obtrac_after_model,
    obtrac_before_tool,
    obtrac_after_tool,
)
```

---

## 6. Step 2 — Configure ObTrac

Call `obtrac_config()` once at module load in your `agent.py`.

```python
from obtrac_sdk import obtrac_config

obtrac_config(
    project="my-adk-app",           # shows up as a project in the dashboard
    backend_url="http://localhost:8100",
    user="satyam",                  # optional — shown in trace detail
    auto_eval=False,                # set True to run RAGAS after each trace
)
```

**Environment variables** (put in `.env`):
```env
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_API_KEY=sk-...
AZURE_OPENAI_ENDPOINT=https://your-resource.cognitiveservices.azure.com/
AZURE_OPENAI_API_VERSION=2024-12-01-preview
```

---

## 7. Step 3 — Wire callbacks into your Agent

```python
import os, sys
from dotenv import load_dotenv
import litellm
litellm.drop_params = True          # required for newer Azure API versions

from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from obtrac_sdk import obtrac_config

# Import ObTrac callbacks
from callbacks import (
    obtrac_before_agent,
    obtrac_after_agent,
    obtrac_before_model,
    obtrac_after_model,
    obtrac_before_tool,
    obtrac_after_tool,
)

load_dotenv()
obtrac_config(project="my-adk-app", backend_url="http://localhost:8100")

_model = LiteLlm(
    model=f"azure/{os.getenv('AZURE_OPENAI_DEPLOYMENT')}",
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_base=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
)

root_agent = Agent(
    name="my_agent",
    model=_model,
    description="My agent description",
    instruction="You are a helpful assistant...",
    tools=[],                               # add your tools here

    # ObTrac hooks — add all six
    before_agent_callback=obtrac_before_agent,
    after_agent_callback=obtrac_after_agent,
    before_model_callback=obtrac_before_model,
    after_model_callback=obtrac_after_model,
    before_tool_callback=obtrac_before_tool,
    after_tool_callback=obtrac_after_tool,
)
```

**`my_agent/__init__.py`**:
```python
from .agent import root_agent
```

---

## 8. Step 4 — Trace individual tools (optional)

Adding `@trace` to tool functions is optional — the `before/after_tool_callback`
already creates tool spans automatically. But `@trace` gives you richer input/output
capture inside the tool function itself.

```python
from google.adk.tools import ToolContext
from obtrac_sdk import trace

@trace(name="web_search", span_type="tool_call")
def web_search(query: str, tool_context: ToolContext) -> dict:
    """Search the web."""
    # your implementation
    return {"results": [...]}

@trace(name="rag_lookup", span_type="retrieval")
def rag_lookup(query: str, top_k: int = 3, tool_context: ToolContext = None) -> dict:
    """Retrieve document chunks."""
    # your vector DB call
    return {"chunks": [...]}
```

> **Note:** `tool_context: ToolContext` must be the last parameter. ADK injects
> it automatically — you never pass it yourself.

---

## 9. Step 5 — Run with adk web

```bash
# From your project root (the folder CONTAINING your agent packages)
cd my_adk_project
adk web .

# Open the ADK UI
open http://localhost:8000

# Open the ObTrac dashboard (in a separate tab)
open http://localhost:3100
```

Send a message in the ADK UI. In the terminal you should see:
```
[ObTrac] trace started | agent=my_agent | session=a1b2c3d4
[ObTrac] model start | azure/gpt-4o
[ObTrac] model done  | tokens={'prompt': 312, 'completion': 87}
[ObTrac] after_agent: trace sent session=a1b2c3d4
[ObTrac] trace stored | id=22d4c249cb77
```

---

## 10. What appears in the dashboard

### Traces page (`/traces`)
Each conversation turn = one Trace row. Click a trace to see:

| Field | Source |
|---|---|
| **Query** | Last user message in the session |
| **Answer** | Agent's final `is_final_response()` event |
| **Latency** | `before_agent` → `after_agent` wall time |
| **Span Tree** | `llm_call` span per LLM call, `tool_name` span per tool used |
| **Tokens** | Extracted from `LlmResponse.usage_metadata` |

### Sessions page (`/sessions`)
All turns with the same ADK `session.id` are grouped as one conversation.
Click a session to see the full chat history as a timeline — Turn 1 → Turn 2 → ...

### Analytics page (`/analytics`)
Latency trends, cost over time, model usage breakdown — all from your ADK traces.

---

## 11. Session continuity (HITL / multi-turn)

ADK maintains `session.id` across turns automatically. ObTrac reads it from
`callback_context.session.id` in every callback — no extra code needed.

Each time the user sends a new message in the same ADK session:
- A new Trace is created in ObTrac
- All traces share the same `session_id`
- Sessions page groups them as "Turn 1 / Turn 2 / Turn 3..."

To start a fresh conversation: click **+ New Session** in the ADK web UI,
or create a new session programmatically.

---

## 12. Using prompt registry

Store and version your prompts in ObTrac instead of hardcoding them.

**Register a prompt** (run once, or via the dashboard Prompts page):
```python
import requests
requests.post("http://localhost:8100/api/v1/prompts", json={
    "name": "my_system_prompt",
    "template": "You are a helpful assistant.\n\nAnswer: {{question}}",
    "description": "Main system prompt",
    "commit_message": "Initial version",
    "created_by": "satyam",
})
```

**Use it in your agent**:
```python
from obtrac_sdk import get_prompt

def build_prompt(question: str) -> str:
    try:
        p = get_prompt("my_system_prompt")   # fetches active version
        return p.render(question=question)
    except Exception:
        return f"Answer: {question}"         # inline fallback
```

> Variables use `{{double_braces}}` — single `{` and `}` are always literal,
> so you can paste JSON examples into templates freely.

**Version your prompts**: every edit in the dashboard creates a new version.
The SDK always fetches the active (latest) version unless you pin one:
```python
p = get_prompt("my_system_prompt", version=2)   # pin to version 2
```

---

## 13. Understanding @trace — How it works and where to put it

`@trace` is ObTrac's universal instrumentation decorator. One decorator handles
everything — sync functions, async functions, async generators, root-level pipelines,
and nested child spans. This section explains the mental model so you know exactly
where to put it and what you will see in the dashboard.

---

### The core concept: Root vs. Child

Every time a `@trace`-decorated function is called, ObTrac checks one thing:

> **Is there already an active Trace in the current execution context?**

- **No active Trace** → `@trace` creates a **root Trace**. This is the top-level
  record that appears as a row in the Traces page. It holds query, answer, cost,
  latency, and evaluation scores for the entire operation.

- **Active Trace exists** → `@trace` creates a **child Span** inside it. Spans
  are the steps visible in the Span Tree on the Trace Detail page. They share the
  same Trace ID and are nested under the root.

This detection is fully automatic — you do not configure it. The same decorator
behaves differently depending on the call stack at runtime.

```
User message arrives
    │
    ▼
@trace  ← no active Trace → creates ROOT Trace
    │
    ├── @trace  ← active Trace exists → creates SPAN (retrieval)
    │
    ├── @trace  ← active Trace exists → creates SPAN (generation)
    │       │
    │       └── @trace  ← nested → creates SPAN (tool_call)
    │
    └── Trace finalized → sent to ObTrac backend
```

---

### Where to put @trace in a Google ADK project

In an ADK project, the callbacks handle the outermost Trace automatically — you
do not need `@trace` on your agent class. Where `@trace` adds value is on the
**functions your agent calls**: your tools, your retrieval logic, your LLM
wrapper functions, your post-processing steps.

Think of it in three layers:

```
LAYER 1 — ADK callbacks handle this automatically
─────────────────────────────────────────────────
before_agent_callback  →  opens root Trace
after_agent_callback   →  closes root Trace, sends to backend
before_model_callback  →  opens llm_call Span
after_model_callback   →  closes llm_call Span with tokens
before_tool_callback   →  opens tool Span
after_tool_callback    →  closes tool Span

LAYER 2 — Put @trace here (inside your tool functions)
──────────────────────────────────────────────────────
@trace on your retrieval function   →  retrieval Span
@trace on your LLM wrapper          →  generation Span with cost
@trace on your post-processing      →  custom Span

LAYER 3 — Optionally put @trace here (utility functions)
─────────────────────────────────────────────────────────
@trace on a re-ranker               →  custom Span
@trace on a validator               →  custom Span
```

The ADK tool callback (`before_tool_callback`) already creates a span for
every tool call. Adding `@trace` inside the tool function creates a **nested**
span with richer input/output detail. Both are valid — use one or the other,
not both, to avoid double-counting.

---

### Function types — all handled automatically

`@trace` inspects the function at decoration time and wraps it appropriately.
You write your function naturally; `@trace` adapts to it.

**Regular (sync) function:**
```python
@trace(name="my_step", span_type="custom")
def process_document(text: str) -> str:
    # runs synchronously
    return cleaned_text
```

**Async coroutine:**
```python
@trace(name="fetch_context", span_type="retrieval")
async def fetch_context(query: str) -> list:
    # awaited by the caller
    results = await vector_db.search(query)
    return results
```

**Async generator (streaming):**
```python
@trace(name="stream_response", span_type="generation")
async def stream_response(prompt: str):
    # yields events one at a time — ADK agents often look like this
    async for chunk in llm.stream(prompt):
        yield chunk
```

All three produce the same kind of Span in the dashboard. The difference is only
how Python executes them — `@trace` handles the wrapping internally.

---

### The span_type parameter — what to use when

`span_type` controls how the span is categorized and displayed in the dashboard.
It also affects which metrics are auto-calculated (e.g. token costs are only
auto-estimated for `generation` and `agent` types).

| span_type | When to use |
|---|---|
| `"retrieval"` | Any function that searches a vector DB, document store, or index. The return value is treated as retrieved context for RAGAS evaluation. |
| `"generation"` | Any function that calls an LLM and returns text. Token counting and cost calculation are applied. |
| `"tool_call"` | Any ADK tool function — the function your agent calls via its `tools=[...]` list. |
| `"agent"` | The outermost function of a pipeline or sub-agent. In root mode this becomes the Trace name. |
| `"embedding"` | A function that calls an embedding model. |
| `"planning"` | A reasoning or planning step before execution. |
| `"custom"` | Anything else — utility functions, validators, post-processors. |

---

### Field mappings — connecting function args to Trace fields

When `@trace` runs in **root mode** (no active trace), it needs to know which
function argument is the user query, which is the retrieved context, and which
is the final answer. These are the fields that appear in the Trace Detail page
and are used for RAGAS evaluation.

You tell `@trace` about them using field mapping parameters:

| Parameter | What it maps | Maps to |
|---|---|---|
| `query="arg_name"` | The function argument containing the user's question | `trace.query` |
| `context="arg_name"` | The argument containing retrieved document text | `trace.context` |
| `response="arg_name"` | The argument (or `"return"`) containing the LLM's answer | `trace.answer` |
| `ground_truth="arg_name"` | The argument containing the expected correct answer | `trace.ground_truth` |

The special value `"return"` means "use the function's return value":

```python
@trace(
    name="rag_pipeline",
    span_type="agent",
    query="user_question",       # maps the 'user_question' argument
    context="retrieved_docs",    # maps the 'retrieved_docs' argument
    response="return",           # maps the function's return value
    ground_truth="expected_ans", # maps the 'expected_ans' argument
)
def rag_pipeline(user_question, retrieved_docs, expected_ans=None):
    answer = llm.generate(user_question, retrieved_docs)
    return answer
```

In **child mode** (active trace exists), these field mappings propagate their
values up to the parent Trace — so a retrieval child span can populate
`trace.context` for the root Trace:

```python
@trace(name="retrieve", span_type="retrieval", context="return")
def retrieve(query, db):
    # return value → automatically added to the parent trace's context field
    return db.search(query)
```

---

### metrics and ground_truth — for RAGAS evaluation

When `auto_eval=True` in `obtrac_config()`, ObTrac runs RAGAS evaluation after
each root Trace. The `metrics` parameter controls which metrics run for this
specific function, overriding the global default.

```python
obtrac_config(
    project="my-app",
    auto_eval=True,
    default_metrics=["faithfulness"],   # runs on all traces by default
)

@trace(
    name="rag_pipeline",
    span_type="agent",
    query="question",
    response="return",
    ground_truth="expected",   # required for answer_correctness
    metrics=["faithfulness", "answer_relevancy", "answer_correctness"],
)
def rag_pipeline(question, expected=None):
    return generate(question)
```

Available metrics:

| Metric | Requires ground_truth |
|---|---|
| `faithfulness` | No — measures if answer is grounded in context |
| `answer_relevancy` | No — measures if answer addresses the question |
| `context_precision` | No — measures if retrieved context is relevant |
| `context_recall` | Yes — measures if context covers the answer |
| `answer_correctness` | Yes — measures factual correctness vs expected answer |
| `answer_similarity` | Yes — semantic similarity to expected answer |

---

### cost — token pricing per function

Add cost tracking to any generation span:

```python
@trace(
    name="generate_answer",
    span_type="generation",
    cost={
        "input_token_cost": 0.003,   # $ per 1K input tokens
        "output_token_cost": 0.012,  # $ per 1K output tokens
    }
)
def generate_answer(prompt: str) -> str:
    return llm.call(prompt)
```

If a LiteLLM response object is returned, ObTrac reads the actual cost from it
directly. The `cost` parameter is used as a fallback when the LLM client does
not report cost.

---

### Nesting — how spans build the tree

The Span Tree in the Trace Detail page shows the call hierarchy. The deeper you
nest `@trace`-decorated functions, the deeper the tree. There is no limit.

```python
@trace(name="full_pipeline", span_type="agent")   # ROOT TRACE
def full_pipeline(question):

    docs = retrieve(question)      # ← SPAN: retrieval
    answer = generate(question, docs)  # ← SPAN: generation
                                       #     └── SPAN: llm_api_call (if nested)
    return answer

@trace(name="retrieve", span_type="retrieval", context="return")
def retrieve(query):
    return vector_db.search(query)

@trace(name="generate", span_type="generation")
def generate(question, context):
    prompt = build_prompt(question, context)
    return call_llm(prompt)          # ← SPAN: tool_call (if @trace on call_llm)
```

Dashboard view of the above:
```
Trace: full_pipeline  3200ms  $0.0024
  ├── retrieve         45ms
  └── generate        3155ms
        └── call_llm  3100ms
```

---

### In an ADK project specifically — recommended placement

```
your_agent/
├── agent.py         ← NO @trace here. ADK callbacks handle the root Trace.
├── tools/
│   ├── search.py    ← @trace(span_type="tool_call")  on each tool function
│   ├── retrieval.py ← @trace(span_type="retrieval")  on vector search functions
│   └── calculator.py← @trace(span_type="tool_call")  on calculator functions
└── utils/
    ├── llm_client.py← @trace(span_type="generation") on your LLM wrapper
    └── reranker.py  ← @trace(span_type="custom")     on post-processing
```

**Do NOT put `@trace` on:**
- Your ADK `Agent` class or its `instruction` / `description`
- The `root_agent` variable itself
- ADK internal methods

**DO put `@trace` on:**
- Every tool function in your `tools=[...]` list
- Any helper function called from within a tool
- Your LLM wrapper if you have one (not needed if using ADK's built-in model)
- Your retrieval / embedding functions
- Any multi-step processing function

---

### Summary

| Situation | What to do |
|---|---|
| Top-level pipeline, no framework | Put `@trace` on the outermost function → becomes root Trace |
| Using ADK callbacks | Don't add `@trace` for the root — callbacks handle it |
| Tool function | Add `@trace(span_type="tool_call")` → appears as child Span |
| Retrieval function | Add `@trace(span_type="retrieval", context="return")` → context flows to root |
| LLM call wrapper | Add `@trace(span_type="generation", cost={...})` → token tracking |
| Utility / post-processing | Add `@trace(span_type="custom")` → visible in Span Tree |
| Async function | Same decorator — `@trace` auto-detects and wraps correctly |
| Async generator / streaming | Same decorator — `@trace` wraps the generator without breaking yield |

---

## 14. Full working example

```python
# my_agent/agent.py
import os
import sys

# Ensure project root (containing callbacks/, tools/) is on sys.path
_AGENT_DIR = os.path.dirname(os.path.dirname(__file__))
if _AGENT_DIR not in sys.path:
    sys.path.insert(0, _AGENT_DIR)

from dotenv import load_dotenv
import litellm
litellm.drop_params = True

from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import ToolContext

from obtrac_sdk import obtrac_config, trace, get_prompt
from callbacks import (
    obtrac_before_agent, obtrac_after_agent,
    obtrac_before_model, obtrac_after_model,
    obtrac_before_tool, obtrac_after_tool,
)

load_dotenv()

obtrac_config(
    project="my-adk-app",
    backend_url="http://localhost:8100",
    user="satyam",
    auto_eval=False,
)

# --- Tool ---
@trace(name="calculator", span_type="tool_call")
def calculator(expression: str, tool_context: ToolContext) -> dict:
    """Evaluate a math expression."""
    import ast, operator
    # ... safe eval implementation ...
    return {"result": eval(expression), "expression": expression}

# --- Agent ---
root_agent = Agent(
    name="my_agent",
    model=LiteLlm(
        model=f"azure/{os.getenv('AZURE_OPENAI_DEPLOYMENT')}",
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_base=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    ),
    description="A helpful assistant with calculator",
    instruction="Use the calculator tool for any math questions.",
    tools=[calculator],
    before_agent_callback=obtrac_before_agent,
    after_agent_callback=obtrac_after_agent,
    before_model_callback=obtrac_before_model,
    after_model_callback=obtrac_after_model,
    before_tool_callback=obtrac_before_tool,
    after_tool_callback=obtrac_after_tool,
)
```

```python
# my_agent/__init__.py
from .agent import root_agent
```

```bash
# Run
cd my_adk_project
adk web .
# → http://localhost:8000  (ADK UI)
# → http://localhost:3100  (ObTrac dashboard)
```

---

## 15. Troubleshooting

### "No agents found in current folder"
You are running `adk web` from the wrong directory.
Run it from the folder that **contains** your agent packages:
```bash
# WRONG — running from inside the agent
cd my_adk_project/my_agent && adk web .   ❌

# CORRECT — running from project root
cd my_adk_project && adk web .            ✓
# or point to a specific agent
cd my_adk_project && adk web my_agent     ✓
```

### "ModuleNotFoundError: No module named 'callbacks'"
Add this to the top of your `agent.py`:
```python
import os, sys
_ROOT = os.path.dirname(os.path.dirname(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
```

### "unexpected keyword argument 'callback_context'"
Your callback function uses the wrong parameter name. ADK 1.x calls:
```python
before_agent_callback(callback_context=...)
after_agent_callback(callback_context=...)
before_model_callback(callback_context=..., llm_request=...)
after_model_callback(callback_context=..., llm_response=...)
before_tool_callback(tool=..., args=..., tool_context=...)
after_tool_callback(tool=..., args=..., tool_context=..., tool_response=...)
```
Use the exact parameter names above.

### "Unsupported parameter: 'max_tokens'"
Newer Azure API versions require `max_completion_tokens`. Fix:
```python
import litellm
litellm.drop_params = True   # add this before creating LiteLlm
```

### Traces appear but Answer = "N/A"
The agent's response event hasn't been marked `is_final_response()` yet when
`after_agent_callback` fires. This happens if your agent streams partial events.
The answer will be populated from `before_model_callback` fallback instead.

### 0 spans in trace
If the agent answered without using a tool (e.g. "Hi"), there are no tool spans —
that's correct. The `llm_call` span from `before/after_model_callback` should
still appear. Ask a question that forces a tool (e.g. "What is 15% of 4500?").

### Windows: OSError path too long on pip install
Enable long paths in Windows:
```powershell
# Run as Administrator
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
    -Name "LongPathsEnabled" -Value 1
```

---

## 16. Reference — callback signatures

All six callbacks. Copy this block into your `callbacks/__init__.py` imports.

```python
# ADK 1.x exact parameter names (keyword-only as called by ADK internals)

def obtrac_before_agent(callback_context) -> None:
    """Fires once at the start of each agent turn."""

def obtrac_after_agent(callback_context) -> None:
    """Fires once at the end of each agent turn."""

def obtrac_before_model(callback_context, llm_request) -> None:
    """Fires before each LLM API call."""
    # llm_request.model      — model name
    # llm_request.contents   — list of Content (prompt history)

def obtrac_after_model(callback_context, llm_response) -> None:
    """Fires after each LLM API call."""
    # llm_response.content          — Content object with response text
    # llm_response.usage_metadata   — token counts

def obtrac_before_tool(tool, args: dict, tool_context) -> None:
    """Fires before each tool function call."""
    # tool.name   — tool function name
    # args        — dict of arguments passed to the tool

def obtrac_after_tool(tool, args: dict, tool_context, tool_response: dict) -> None:
    """Fires after each tool function call."""
    # tool_response — dict returned by the tool
```

All callbacks return `None` — returning anything else overrides the agent's
normal behavior (useful for mocking/testing but avoid in production).
