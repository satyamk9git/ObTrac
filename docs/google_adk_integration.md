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

Copy `test_gadk/callbacks/` from the ObTrac repo into your project root.
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

## 13. @trace on your own functions

Use `@trace` on any function that runs inside your agent to get child spans.

```python
from obtrac_sdk import trace

# Root trace (when no active trace) — works like @observe
@trace(
    name="full_pipeline",
    span_type="agent",
    query="question",           # arg name → trace.query
    context="retrieved_docs",   # arg name → trace.context
    response="return",          # return value → trace.answer
    ground_truth="expected",    # arg name → trace.ground_truth
    metrics=["faithfulness", "answer_relevancy"],  # RAGAS metrics
)
def full_pipeline(question, retrieved_docs, expected=None):
    return generate(question, retrieved_docs)

# Child span (inside an active trace)
@trace(name="retrieve", span_type="retrieval", context="return")
def retrieve(query, db, k=5):
    return db.search(query, k=k)

# Async functions work identically
@trace(name="generate", span_type="generation",
       cost={"input_token_cost": 0.003, "output_token_cost": 0.012})
async def generate(question, context):
    return await llm.invoke(f"Context: {context}\nQ: {question}")

# Async generators (streaming agents)
@trace(name="stream_agent", span_type="agent")
async def stream_agent(ctx):
    async for event in inner_agent.run(ctx):
        yield event
```

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
