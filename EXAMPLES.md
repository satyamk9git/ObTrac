# ObTrac Examples & Test Scenarios

A complete cookbook of how to use ObTrac with real code examples, edge cases, and test scenarios.

> **Reading this on v0.6.1?** Jump to the [What's New in v0.6](#whats-new-in-v06) section for the new features (auto-create project, async eval, AI insights, prompt regen, period filters).

## Table of Contents

0. [What's New in v0.6](#whats-new-in-v06)
1. [Hello World — Minimal Example](#1-hello-world--minimal-example)
2. [Basic RAG Pipeline](#2-basic-rag-pipeline)
3. [Multi-Agent System](#3-multi-agent-system)
4. [Different Models per Agent](#4-different-models-per-agent)
5. [Async Functions](#5-async-functions)
6. [LangChain Integration](#6-langchain-integration)
7. [LangGraph Integration](#7-langgraph-integration)
8. [Field Mapping (Custom Variable Names)](#8-field-mapping-custom-variable-names)
9. [Manual Token & Cost Override](#9-manual-token--cost-override)
10. [Session Tracking (Multi-Turn Chat)](#10-session-tracking-multi-turn-chat)
11. [Auto-Evaluation Setup](#11-auto-evaluation-setup)
12. [Ground Truth Evaluation](#12-ground-truth-evaluation)
13. [Error Handling](#13-error-handling)
14. [Edge Cases](#14-edge-cases)
15. [Test Scenarios](#15-test-scenarios)

---

## What's New in v0.6

This section covers the SDK and dashboard features added between v0.4.1-stable and v0.6.1. Skip this section if you only need the basic recipes — they all still work.

### 1. Auto-create project from `obtrac_config()`

Before v0.6, your project only appeared in the dashboard *after* you logged the first trace. Now `obtrac_config()` POSTs to the backend on init, so the project shows up immediately.

```python
from obtrac_sdk import obtrac_config

obtrac_config(
    project="my-new-project",     # ← appears in dashboard right away
    backend_url="http://localhost:8100",
    user="satyam",
    auto_create_project=True,     # default — set to False if you want to skip the auto-POST
)
```

The call is **idempotent** (existing projects are returned, not duplicated), has a **2-second timeout**, and **silently fails** if the backend is unreachable so it can't break offline scripts.

### 2. Async evaluation — eval keeps running when you navigate away

Before v0.6, kicking off a multi-LLM RAGAS evaluation locked the trace detail page until it finished (30+ seconds). Navigate away → eval was canceled.

Now when you click **Evaluate**, the dashboard:
1. POSTs to `/evaluation/run-multi-llm-async` and gets back a `job_id` in <100ms
2. Shows an indigo banner: *"You can navigate away — the evaluation will keep running"*
3. Polls `/evaluation/jobs/{job_id}` every 2s
4. The trace page auto-detects in-flight jobs on mount, so reloading or coming back later picks up the spinner

A **"running evals" badge** in the top bar polls every 5s and shows count + dropdown of active jobs across all projects. Click any job → jump to the trace.

### 3. AI insights at three levels

| Level | Where | Endpoint |
|---|---|---|
| **Per-trace** | Click any metric on a trace → Metric Explainer modal | `POST /explain/metric` |
| **Per-project** | Metrics > Overview → "Generate Analysis" | `POST /explain/project-metrics` |
| **Per-correlation** | Metrics > Correlation → "Analyze Metrics" | `POST /explain/correlation` |

All three use your auto-eval LLM as the analyst, return structured JSON (verdict, top issues, root causes, code snippet fixes), and are cached 10 minutes per project.

Example payload from `POST /explain/project-metrics`:

```json
{
  "project": "langgraph-agent",
  "evaluated_traces": 14,
  "worst_metric": "answer_correctness",
  "insights": {
    "health": "critical",
    "headline": "The RAG system is frequently producing incorrect answers despite faithful use of context.",
    "top_issues": [
      {
        "metric": "answer_correctness",
        "severity": "high",
        "pattern": "Answers often address a different plausible question from the same document",
        "root_cause": "Retrieval is fetching the right document but the LLM picks the wrong section"
      }
    ],
    "highest_leverage_fix": {
      "title": "Add a re-ranker between retrieval and generation",
      "description": "...",
      "expected_impact": "answer_correctness from 28.7% → ~65-75%",
      "code_or_config_example": "from cohere import Client\nclient.rerank(query=q, documents=chunks)"
    }
  }
}
```

### 4. AI prompt regeneration with edge-case guidance

When you merge multiple prompt versions, the merge UI now has an optional **"Regenerate with extra guidance"** textarea. Examples of guidance the LLM will respect:

- *"Make sure the prompt handles empty context gracefully"*
- *"Output must be valid JSON"*
- *"Add a constraint to never mention dates"*
- *"Preserve the explicit 'use only provided context' rule from v3"*

Backend accepts an `extra_instructions` field on `POST /prompts/{name}/merge`:

```python
import requests

requests.post(
    "http://localhost:8100/api/v1/prompts/rag_answer/merge",
    json={
        "versions": [2, 3, 4],
        "extra_instructions": "Output must be exactly 3 sentences, no more.",
    },
)
```

### 5. Excel-style trace filters

The **Traces** page now has Excel-like column-header dropdowns:

- **Trace ID, Pipeline, User, Status, Spans** → multi-select with search box
- **Latency** → sort asc/desc
- **Time** → sort asc/desc + From/To date range picker

Filters apply client-side for instant response. The page fetches the most recent 200 traces.

This is purely a UI feature — no SDK changes. But if you have a lot of traces, you'll feel it.

### 6. Period filter on Analytics

The **Analytics** page now has a top-right toggle: **Today / This Week / This Month / Lifetime**. The backend endpoints accept a `period` query param:

```bash
curl "http://localhost:8100/api/v1/analytics/tokens?project=my-app&period=daily"
curl "http://localhost:8100/api/v1/analytics/cost/over-time?project=my-app&period=monthly"
```

Valid values: `daily`, `weekly`, `monthly`, `lifetime`. Default is `lifetime`.

Period boundaries:
- **Daily**: midnight UTC of today
- **Weekly**: Monday 00:00 UTC of this week
- **Monthly**: 1st 00:00 UTC of this month
- **Lifetime**: no filter

### 7. Budget ↔ alert channel mapping with de-dup

Before v0.6, budgets and alert channels were connected by **convention** — channels listened for trigger names like `budget_50` / `budget_80` / `budget_100`, and any project-matching channel that listened for the right name would fire. Easy to set up wrong, easy to miss.

Now budgets have an explicit `alert_channel_ids` list. The flow is:

```python
import requests

# Step 1: Create the alert channel
channel = requests.post("http://localhost:8100/api/v1/alerts/channels", json={
    "name": "Slack #ai-alerts",
    "channel_type": "slack",
    "config": {"url": "https://hooks.slack.com/services/..."},
    "project": "all",
}).json()

# Step 2: Map the channel to a budget
requests.put(f"http://localhost:8100/api/v1/budgets/{budget_id}", json={
    "alert_channel_ids": [channel["id"]],
})

# Now when traces push spend across the budget's thresholds (50, 80, 100),
# Slack receives a message — only ONCE per threshold per period.
```

The **de-dup state** (`last_fired_threshold`, `last_fired_at`) prevents the same threshold from firing twice in one period. A budget at 84% won't spam every trace — it fires once at 80% and stays quiet until you cross 100% or the period rolls over.

### 8. Embedder Config + global semantic GT matching

Before v0.6, semantic ground-truth matching used a hard-coded local `sentence-transformers/all-MiniLM-L6-v2` model. Now you configure your embedder in **Embedder Config**:

```bash
# Add an OpenAI embedder via the CLI
obtrac embedder add \
  --name openai-large \
  --provider openai \
  --model text-embedding-3-large \
  --api-key sk-... \
  --default

# Test it works
obtrac embedder test openai-large
```

Or use the dashboard at http://localhost:3100/embedder.

The semantic GT matcher reads from this config automatically. Cache key includes the embedder ID, so switching defaults invalidates stale vectors.

### 9. Better trace logging error visibility

Previously, when the SDK couldn't reach the backend (network error, 500 response, etc.), it logged at `DEBUG` level — silently swallowed by the default Python logger config. Users wondered why traces weren't showing up.

Now those failures log at `WARNING`:

```
WARNING:obtrac:ObTrac backend rejected trace (HTTP 500) at http://localhost:8100/api/v1/traces — body: {"error":"OperationalError","message":"no such column: traces.session_id","path":"/api/v1/traces"}
```

The backend also has a global exception handler that returns the actual error type and message in 500 responses (instead of FastAPI's generic "Internal Server Error"). So the SDK warning is actually useful.

### 10. Auto-migration on startup

When you upgrade ObTrac, the new version's models may have new columns the old SQLite database doesn't have. Previously this would crash on the first INSERT. Now `init_db()` calls `_add_missing_columns()` which walks every model, compares against the live schema, and runs `ALTER TABLE ADD COLUMN` for anything missing.

It's **idempotent** and **additive only** (never drops or renames). You'll see log lines on the next backend startup after an upgrade:

```
INFO:obtrac:Schema migration: added budgets.alert_channel_ids
INFO:obtrac:Schema migration: added budgets.last_fired_threshold
INFO:obtrac:Schema migration: added budgets.last_fired_at
```

This is what makes the v0.4.1-stable → v0.6.1 upgrade safe without any manual SQL.

### 11. Prompt template syntax (v0.6.4+)

ObTrac uses **Mustache-style double-brace placeholders** for prompt variables. This is a deliberate departure from Python's native `str.format()` because it makes JSON examples in prompts work without any escaping.

#### The rules

| Syntax | Meaning |
|---|---|
| `{{question}}` | Substituted with the value of `question=` kwarg at render time |
| `{` and `}` (single braces) | **Literal characters.** Always passed through unchanged. |
| `{"key": "value"}` | Literal JSON. Just write it as-is. |
| `{{}}` (empty) | Renders as literal `{{}}` — empty placeholders aren't substituted |

Variable names must be valid Python identifiers — letters, digits, and underscores only.

#### ✓ Just write JSON examples directly

```python
template = """Return JSON in this format:
{
  "answer": "your answer",
  "confidence": 0.9
}

Question: {{question}}
Context: {{context}}
"""
```

That's it. No escaping. The single `{` and `}` around the JSON example are literal characters. Only `{{question}}` and `{{context}}` get substituted.

#### Compared to other templating systems

| System | Variable syntax | JSON in prompts |
|---|---|---|
| **ObTrac (v0.6.4+)** | `{{var}}` | Just write it |
| **Python `str.format()`** | `{var}` | Must escape `{` as `{{` and `}` as `}}` |
| **Mustache / Handlebars** | `{{var}}` | Just write it |
| **Jinja2** | `{{ var }}` | Just write it (with spaces) |
| **f-strings** | `{var}` | Must escape (same as `str.format()`) |

ObTrac follows the Mustache convention because it's the most ergonomic for LLM prompts, which frequently contain JSON examples in their instructions.

#### Migrating from v0.6.3 and earlier

If you have prompts written in the old single-brace style (`{question}`), they will **silently fail to render** in v0.6.4+ — the validator will warn you with a soft warning identifying the legacy placeholders, but the template will technically be "valid" (because no errors are raised). The renderer just won't substitute them.

To migrate, replace `{var}` with `{{var}}` for every declared variable:

```python
# Old (v0.6.3 and earlier — no longer renders)
template = "Hello {name}, your context is: {context}"

# New (v0.6.4+)
template = "Hello {{name}}, your context is: {{context}}"
```

The dashboard validator on the prompt edit form will show a yellow warning if it sees single-brace placeholders, so you can spot them at a glance.

#### Auto-validation in the dashboard

ObTrac validates your template **as you type** in the prompt create form and editor. The backend extracts every `{{varname}}` and verifies it can render with placeholder values. You'll see one of three states:

1. 🟢 **Green checkmark + variable list** — template is valid, here are the variables it'll substitute
2. 🟡 **Yellow warning** — looks suspicious (e.g., legacy single-brace placeholders found, or empty `{{}}`) but allowed
3. 🔴 **Red error** — template won't render at all, save is blocked

You can also call the validation endpoint directly:

```python
import requests

r = requests.post(
    "http://localhost:8100/api/v1/prompts/validate",
    json={"template": "Hello {{name}}, return JSON: {\"key\": \"value\"}"},
)
print(r.json())
# {
#   "is_valid": true,
#   "variables": ["name"],
#   "warnings": [],
#   "errors": []
# }
```

Useful for CI scripts that lint your prompt files before committing them.

#### A complete example

```python
# templates/extract_employee.txt
template = """You are an information extraction assistant. Use ONLY the provided context to answer the question. Return your answer as a JSON object in this exact format (no preamble, no markdown):

{
  "name": "<full name>",
  "dept": "<department>",
  "id": "<employee id>"
}

If any field is not in the context, set its value to null.

Context:
{{context}}

Question:
{{question}}

JSON answer:"""
```

In code:

```python
from obtrac_sdk import get_prompt

prompt = get_prompt("extract_employee")
text = prompt.render(
    context="Satyam Verma (id: E1029) works in the Data & GenAI Engineering department.",
    question="Who is Satyam and what does he do?",
)

# `text` now contains the rendered prompt with the JSON example LITERAL
# (not substituted) and {{context}} / {{question}} replaced with the values
# you passed.
```

The rendered output:

```
You are an information extraction assistant. Use ONLY the provided context to answer the question. Return your answer as a JSON object in this exact format (no preamble, no markdown):

{
  "name": "<full name>",
  "dept": "<department>",
  "id": "<employee id>"
}

If any field is not in the context, set its value to null.

Context:
Satyam Verma (id: E1029) works in the Data & GenAI Engineering department.

Question:
Who is Satyam and what does he do?

JSON answer:
```

Notice the JSON example is preserved exactly as written — no escaping was needed.

---

## 1. Hello World — Minimal Example

**Goal:** Trace a simple function with 5 lines of code.

```python
from obtrac_sdk import obtrac_config, trace

obtrac_config(project="hello-world", user="satyam")

@trace(name="say_hello")
def say_hello(name):
    return f"Hello, {name}!"

print(say_hello("Satyam"))
```

**Run:**
```bash
python hello.py
```

**Result:** Open http://localhost:3100 → see project `hello-world` with 1 trace.

---

## 2. Basic RAG Pipeline

**Goal:** Trace a complete RAG flow with retrieval + generation.

```python
from obtrac_sdk import obtrac_config, trace, observe

obtrac_config(
    project="basic-rag",
    user="satyam",
    backend_url="http://localhost:8100",
)

# Sample data
DOCS = [
    "Python is a high-level programming language.",
    "Python supports OOP, functional, and procedural programming.",
    "Python has a large standard library.",
]

@trace(name="retrieve", span_type="retrieval")
def retrieve(query, k=2):
    # Simple keyword match (replace with FAISS/Pinecone in real app)
    matches = [d for d in DOCS if any(w in d.lower() for w in query.lower().split())]
    return matches[:k]

@trace(name="generate", span_type="generation",
       model="gpt-4o",
       cost={"input_token_cost": 0.0025, "output_token_cost": 0.01})
def generate(query, context):
    # Replace with actual LLM call
    return f"Based on the context, {query.lower()} relates to: {context[0] if context else 'unknown'}"

@observe(name="rag_pipeline", metrics=["faithfulness", "answer_relevancy"])
def pipeline(query):
    docs = retrieve(query)
    answer = generate(query, docs)
    return answer

if __name__ == "__main__":
    print(pipeline("What is Python?"))
```

**Edge case:** Empty retrieval results
```python
print(pipeline("Quantum entanglement"))   # No matches → empty docs → low faithfulness
```

---

## 3. Multi-Agent System

**Goal:** Trace a planner → executor → reviewer agent loop.

```python
from obtrac_sdk import obtrac_config, trace, observe

obtrac_config(project="multi-agent", user="satyam")

@trace(name="planner", span_type="generation", model="gpt-4o")
def planner(query):
    # Returns a list of tools to call
    return ["search", "summarize"] if "summarize" in query else ["search"]

@trace(name="tool_search", span_type="tool_call")
def search(query):
    return [f"result for {query}"]

@trace(name="tool_summarize", span_type="generation", model="gpt-4o-mini",
       cost={"input_token_cost": 0.00015, "output_token_cost": 0.0006})
def summarize(text):
    return f"Summary: {text[:50]}"

@trace(name="executor", span_type="custom")
def executor(plan, query):
    results = []
    for tool in plan:
        if tool == "search":
            results.append(search(query))
        elif tool == "summarize":
            results.append(summarize(str(results)))
    return results

@trace(name="reviewer", span_type="generation", model="gpt-4o")
def reviewer(query, results):
    return {"score": 0.9, "answer": str(results)}

@observe(name="agent_pipeline")
def agent(query):
    plan = planner(query)
    results = executor(plan, query)
    review = reviewer(query, results)
    return review["answer"]

if __name__ == "__main__":
    print(agent("Find and summarize info on Python"))
```

**What you'll see in the dashboard:**
- 1 root trace `agent_pipeline`
- 5 child spans: `planner`, `executor`, `tool_search`, `tool_summarize`, `reviewer`
- Span tree shows parent-child relationships

---

## 4. Different Models per Agent

**Goal:** Use GPT-4o for the planner and Gemini Flash for cheap retrieval.

```python
from obtrac_sdk import obtrac_config, trace, observe

obtrac_config(project="multi-model", user="satyam")

# GPT-4o — expensive but smart for planning
@trace(name="planner", span_type="generation",
       model="gpt-4o",
       cost={"input_token_cost": 0.0025, "output_token_cost": 0.01})
def plan(query):
    return f"Plan for {query}"

# Gemini Flash — cheap for bulk retrieval
@trace(name="retriever", span_type="generation",
       model="gemini-2.5-flash",
       cost={"input_token_cost": 0.00015, "output_token_cost": 0.0006})
def retrieve(query):
    return [f"doc {i}" for i in range(5)]

# Claude Sonnet — for the final review
@trace(name="reviewer", span_type="generation",
       model="claude-sonnet-4-5",
       cost={"input_token_cost": 0.003, "output_token_cost": 0.015})
def review(answer):
    return f"Reviewed: {answer}"

@observe(name="multi_model_pipeline")
def pipeline(query):
    p = plan(query)
    docs = retrieve(query)
    return review(f"{p} with {len(docs)} docs")

pipeline("test query")
```

**Dashboard view:**
- **Metrics → By Model** tab → see avg cost per model
- Each span shows its own model name and cost

---

## 5. Async Functions

**Goal:** Trace async/await code (e.g., async LLM calls).

```python
import asyncio
from obtrac_sdk import obtrac_config, trace, observe

obtrac_config(project="async-app", user="satyam")

@trace(name="async_fetch", span_type="retrieval")
async def fetch_async(query):
    await asyncio.sleep(0.5)  # Simulate API call
    return [f"doc for {query}"]

@trace(name="async_llm", span_type="generation", model="gpt-4o")
async def llm_async(query, docs):
    await asyncio.sleep(0.3)
    return f"Answer using {len(docs)} docs"

@observe(name="async_pipeline")
async def pipeline_async(query):
    docs = await fetch_async(query)
    return await llm_async(query, docs)

# Run it
async def main():
    answer = await pipeline_async("What is async?")
    print(answer)

asyncio.run(main())
```

**Note:** `@trace` and `@observe` automatically detect async functions.

---

## 6. LangChain Integration

```python
import os
from dotenv import load_dotenv
from obtrac_sdk import obtrac_config, trace, observe

load_dotenv()

from langchain_community.chat_models import ChatLiteLLM
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

obtrac_config(project="langchain-rag", user="satyam")

llm = ChatLiteLLM(
    model=f"azure/{os.getenv('AZURE_OPENAI_DEPLOYMENT')}",
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_base=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
)
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

# Build a tiny vector store
vectorstore = FAISS.from_texts(
    ["Python is a programming language.", "Python supports OOP."],
    embeddings,
)

@trace(name="lc_retrieve", span_type="retrieval", query="q", context="return")
def retrieve(q):
    return [d.page_content for d in vectorstore.similarity_search(q, k=2)]

@trace(name="lc_generate", span_type="generation", model="gpt-4o",
       cost={"input_token_cost": 0.0025, "output_token_cost": 0.01})
def generate(query, context):
    prompt = ChatPromptTemplate.from_template(
        "Answer using context.\n\nContext: {context}\n\nQuestion: {q}\n\nAnswer:"
    )
    chain = prompt | llm | StrOutputParser()
    return chain.invoke({"context": "\n".join(context), "q": query})

@observe(name="langchain_pipeline", metrics=["faithfulness", "answer_relevancy"])
def pipeline(question):
    docs = retrieve(question)
    return generate(question, docs)

print(pipeline("What is Python?"))
```

---

## 7. LangGraph Integration

```python
import os
from typing import TypedDict
from dotenv import load_dotenv
from obtrac_sdk import obtrac_config, trace, observe

load_dotenv()

from langchain_community.chat_models import ChatLiteLLM
from langgraph.graph import StateGraph, END

obtrac_config(project="langgraph-pipeline", user="satyam")

llm = ChatLiteLLM(
    model=f"azure/{os.getenv('AZURE_OPENAI_DEPLOYMENT')}",
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_base=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
)

class State(TypedDict):
    query: str
    research: str
    answer: str

@trace(name="research_node", span_type="generation", model="gpt-4o")
def research(state: State) -> State:
    state["research"] = llm.invoke(f"Research: {state['query']}").content
    return state

@trace(name="answer_node", span_type="generation", model="gpt-4o")
def answer(state: State) -> State:
    state["answer"] = llm.invoke(f"Based on: {state['research']}\n\nAnswer: {state['query']}").content
    return state

graph = StateGraph(State)
graph.add_node("research", research)
graph.add_node("answer", answer)
graph.set_entry_point("research")
graph.add_edge("research", "answer")
graph.add_edge("answer", END)
app = graph.compile()

@observe(name="langgraph_pipeline", metrics=["faithfulness"])
def run(query):
    result = app.invoke({"query": query})
    return result["answer"]   # Return the answer text, not the dict!

print(run("What is RAG?"))
```

**Key gotcha:** LangGraph returns a state dict. You **must** return the actual answer text from the `@observe` function, not the full state, or RAGAS evaluation will fail.

---

## 8. Field Mapping (Custom Variable Names)

**Goal:** Use any variable names in your code, but tell ObTrac which is which.

```python
from obtrac_sdk import obtrac_config, trace, observe

obtrac_config(project="custom-names", user="satyam")

# Variables don't have to be called query/context/answer
@trace(name="search", span_type="retrieval",
       query="q",              # "q" is the query
       context="return")        # return value = retrieved context
def search(q, top_k=5):
    return [f"doc {i}" for i in range(top_k)]

@trace(name="answer", span_type="generation", model="gpt-4o",
       query="q",
       context="ctx",
       response="return")
def answer(q, ctx):
    return f"Answer to {q} using {len(ctx)} docs"

@observe(name="pipeline",
         query="user_input",   # First arg is "user_input", not "query"
         answer="return")
def pipeline(user_input, db):
    docs = search(user_input)
    return answer(user_input, docs)

pipeline("test")
```

**When to use field mapping:**
- Your function args have non-standard names (`q`, `prompt`, `text`, etc.)
- Multiple args could be the query (need to disambiguate)
- The context comes from a function arg, not from retrieval spans

---

## 9. Manual Token & Cost Override

**Goal:** Override auto-counted tokens with exact values from your LLM provider.

```python
from obtrac_sdk import obtrac_config, trace, log_llm_usage
from openai import AzureOpenAI

obtrac_config(project="manual-tokens", user="satyam")

client = AzureOpenAI(...)

@trace(name="generate", span_type="generation", model="gpt-4o")
def generate(prompt):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
    )

    # Override auto-captured tokens with exact counts
    log_llm_usage(
        tokens={
            "prompt": response.usage.prompt_tokens,
            "completion": response.usage.completion_tokens,
        },
        cost=0.0035,                # Optional: exact cost from provider
        model="gpt-4o",
    )

    return response.choices[0].message.content

generate("What is the capital of France?")
```

---

## 10. Session Tracking (Multi-Turn Chat)

**Goal:** Group multiple traces into one conversation.

```python
from obtrac_sdk import obtrac_config, trace, observe
import uuid

# Create a unique session per user/conversation
session = f"user_satyam_{uuid.uuid4().hex[:8]}"

obtrac_config(
    project="chatbot",
    user="satyam",
    session_id=session,    # All traces in this run will share this session
)

@observe(name="chat")
def chat(message, history=[]):
    response = f"Echo: {message}"
    history.append((message, response))
    return response

# Simulate a conversation
history = []
chat("Hi", history)
chat("What's the weather?", history)
chat("Bye", history)
```

**Dashboard:** Go to **Sessions** → see all 3 turns grouped under one session.

---

## 11. Auto-Evaluation Setup

**Goal:** Automatically run RAGAS evaluation after every pipeline run.

### Step 1: Configure an LLM with auto-eval

In the dashboard:
1. Go to **LLM Config** → click **+ Add LLM**
2. Fill in your Azure OpenAI credentials
3. Check **"Use for Auto-Evaluation"**
4. Save

### Step 2: Enable in code

```python
obtrac_config(
    project="auto-eval-app",
    user="satyam",
    auto_eval=True,    # Enable auto-eval
)

@observe(name="pipeline",
         metrics=["faithfulness", "answer_relevancy"])  # Which metrics to run
def pipeline(query):
    # ... your pipeline
    return answer
```

### Step 3: Run it

```python
pipeline("What is Python?")
# Trace appears with eval_status="pending"
# Backend runs eval automatically using your auto-eval LLM
# Trace updates to eval_status="completed" with metrics
```

**Watch in dashboard:** Metrics column shows spinner → then scores.

---

## 12. Ground Truth Evaluation

**Goal:** Evaluate against expected answers for `answer_correctness`.

```python
from obtrac_sdk import obtrac_config, observe

obtrac_config(project="gt-eval", user="satyam", auto_eval=True)

@observe(name="qa_pipeline",
         query="question",
         ground_truth="expected",
         metrics=["faithfulness", "answer_correctness"])
def qa(question, expected=None):
    # Your pipeline
    return f"Generated answer for {question}"

# Pass ground truth
qa("What is 2+2?", expected="4")
qa("Capital of France?", expected="Paris")
```

**Or upload ground truth via Resources page:**
1. Create CSV: `question,ground_truth`
2. Go to **Resources** → upload
3. Backend auto-matches questions to ground truth during eval

---

## 13. Error Handling

**Goal:** Failed traces are still logged with error status.

```python
from obtrac_sdk import obtrac_config, trace, observe

obtrac_config(project="error-test", user="satyam")

@trace(name="risky_step", span_type="generation")
def risky_step(query):
    if query == "fail":
        raise ValueError("Simulated failure")
    return "OK"

@observe(name="pipeline")
def pipeline(query):
    return risky_step(query)

try:
    pipeline("fail")
except ValueError:
    pass

# Check the dashboard — the trace appears with status="error" (red badge)
# The error message is captured in the trace
```

---

## 14. Edge Cases

### A. Function returns None
```python
@trace(name="returns_none")
def returns_none():
    return None
# Captured as outputs={"result": "None"}
```

### B. Function returns a dict
```python
@trace(name="returns_dict")
def returns_dict():
    return {"answer": "yes", "confidence": 0.9}
# Serialized as JSON in span outputs
```

### C. Function with no arguments
```python
@trace(name="no_args")
def no_args():
    return "static response"
# Inputs = {} (empty)
```

### D. Function with **kwargs only
```python
@trace(name="kwargs_only")
def kwargs_only(**kwargs):
    return kwargs
# Inputs captured from kwargs
```

### E. Nested @observe (only outermost is the root)
```python
@observe(name="outer")
def outer():
    return inner()  # inner's @observe is treated as nested span

@observe(name="inner")
def inner():
    return "data"
# outer creates root trace, inner becomes a child span (not a separate trace)
```

### F. Calling traced function from untraced context
```python
@trace(name="standalone")
def standalone():
    return "data"

# No @observe wrapper — span is created but has no parent trace
# Still captured in backend as orphan span (only if a trace exists)
standalone()
```

### G. Very long output (>5000 chars)
```python
@trace(name="long_output")
def long_output():
    return "x" * 10000
# Output is truncated to 5000 chars in storage to avoid bloat
```

### H. Non-string return value
```python
@trace(name="returns_object")
def returns_object():
    return SomeCustomClass()
# Falls back to str(obj)[:5000]
```

---

## 15. Test Scenarios

### Test 1: Verify trace appears in dashboard

```python
from obtrac_sdk import obtrac_config, observe

obtrac_config(project="test-1", user="tester")

@observe(name="test_pipeline")
def test():
    return "hello"

test()
```

**Check:** Open http://localhost:3100 → "test-1" project → 1 trace.

### Test 2: Verify low faithfulness on hallucination

```python
@observe(name="halluc_test", metrics=["faithfulness"])
def halluc_test(query, context):
    # Intentionally return something not in context
    return "The answer is 42, even though context says nothing about numbers."

halluc_test("What is the meaning?", "Cats are animals.")
```

**Expected:** Faithfulness < 0.3.

### Test 3: Verify high score on grounded answer

```python
@observe(name="grounded_test", metrics=["faithfulness"])
def grounded_test(query, context):
    # Answer fully grounded in context
    return "Cats are animals, as stated in the context."

grounded_test("What is a cat?", "Cats are animals.")
```

**Expected:** Faithfulness > 0.8.

### Test 4: Verify cost calculation

```python
@trace(name="cost_test", model="gpt-4o",
       cost={"input_token_cost": 0.0025, "output_token_cost": 0.01})
def cost_test():
    # Returns 100-token response
    return "word " * 100
```

**Expected cost:** ~$0.001 (depends on tiktoken count).

### Test 5: Verify multi-LLM comparison

In dashboard:
1. Add 2 LLMs in **LLM Config**
2. Open any trace → **Run RAGAS Evaluation**
3. Select both LLMs → click Run
4. See side-by-side comparison

### Test 6: Verify session grouping

```python
import uuid
session = f"test_session_{uuid.uuid4().hex[:8]}"

obtrac_config(project="session-test", user="tester", session_id=session)

@observe(name="turn")
def turn(msg):
    return f"reply: {msg}"

turn("hi")
turn("how are you")
turn("bye")
```

**Check:** Sessions page → see 3 turns grouped.

### Test 7: Verify error trace logging

```python
@observe(name="error_test")
def error_test():
    raise RuntimeError("Test error")

try:
    error_test()
except:
    pass
```

**Check:** Trace appears with status="error".

### Test 8: Verify SQL editor

In dashboard:
1. Go to **SQL Editor**
2. Run: `SELECT COUNT(*) FROM traces WHERE project='test-1'`
3. Should return the count.

### Test 9: Verify search (Ctrl+K)

1. Press **Ctrl+K** anywhere
2. Type "test" → see matching traces
3. Click one → navigate to detail.

### Test 10: Verify export

1. Go to **Metrics**
2. Click **Export CSV**
3. CSV downloads with all metrics.

---

## Common Mistakes to Avoid

1. **Returning a dict from `@observe`** — RAGAS expects an answer string. Extract `result["answer"]` before returning.

2. **Forgetting `@observe` on the pipeline** — `@trace` alone creates orphan spans. Always wrap with `@observe`.

3. **Setting cost in both global config and `@trace`** — `@trace` cost wins. Only set in one place.

4. **Using auto-eval without configuring an LLM** — Set "Use for Auto-Evaluation" on at least one LLM in the dashboard.

5. **Not loading `.env`** — Call `load_dotenv()` at the top of your script before reading env vars.

6. **Same session_id across users** — Each user/conversation should have a unique session_id.

7. **Forgetting to restart Streamlit after `.env` changes** — Streamlit caches env vars at startup.

---

## Performance Tips

- **Use production frontend** (`npm run build && npm start`) — 10x faster than dev mode.
- **Disable auto-eval in production** unless you really need it (it adds latency).
- **Use SQLite for dev**, **PostgreSQL for production**.
- **Truncate long traces** — ObTrac auto-truncates to 5000 chars per field.
- **Use sampling** — Only `@observe` 10% of traces if you have very high traffic.

---

For framework setup and basic usage, see [README.md](README.md).
