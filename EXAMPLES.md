# ObTrac Examples & Test Scenarios

A complete cookbook of how to use ObTrac with real code examples, edge cases, and test scenarios.

## Table of Contents

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
