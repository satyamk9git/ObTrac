"""
One-time prompt setup — registers all prompts used by the test app
in the ObTrac registry.  Run once before starting the Streamlit app:

    python demos/langgraph_streamlit_rag/prompts_setup.py

Safe to run multiple times (skips prompts that already exist).
"""

import requests
import sys

API = "http://localhost:8100/api/v1"

PROMPTS = [
    {
        "name": "rag_answer",
        "description": "Main RAG answer generation prompt",
        "tags": ["rag", "generation"],
        "commit_message": "Initial version — mustache syntax",
        "template": """You are a helpful assistant. Answer the question based ONLY on the provided context.
If the context does not contain enough information, say 'I don't have enough information to answer that.'

Context:
{{context}}

Question: {{question}}

Answer clearly and concisely in 2-4 sentences.""",
    },
    {
        "name": "review_prompt",
        "description": "Answer quality reviewer",
        "tags": ["rag", "review"],
        "commit_message": "Initial version",
        "template": """Review this answer for accuracy, completeness, and clarity.

Question: {{question}}
Answer: {{answer}}

Respond in one sentence starting with 'Good:' or 'Needs improvement:' followed by brief feedback.""",
    },
    {
        "name": "agent_system",
        "description": "Tool-selection system prompt for the multi-tool agent",
        "tags": ["agent", "tools"],
        "commit_message": "Initial version",
        "template": """You are a helpful assistant with access to these tools:
- calculator: evaluate math expressions (e.g. "25% of 8000")
- get_datetime: get current date and time
- web_search: search for information on any topic
- summarize: summarize a piece of text
- unit_converter: convert between units (km/miles, kg/lbs, celsius/fahrenheit, usd/inr)
- none: answer directly without a tool

Given the user's question, respond with ONLY a JSON object:
{"tool": "<tool_name>", "input": "<what to pass to the tool>"}

Question: {{question}}""",
    },
    {
        "name": "final_answer",
        "description": "Final answer generation after tool use",
        "tags": ["agent", "generation"],
        "commit_message": "Initial version",
        "template": """You are a helpful, concise assistant.

User question: {{question}}
Tool used: {{tool_name}}
Tool result: {{tool_result}}

Write a clear, natural answer. Do not mention the tool name explicitly.""",
    },
    {
        "name": "simple_chat",
        "description": "Simple conversational Q&A prompt",
        "tags": ["chat"],
        "commit_message": "Initial version",
        "template": """You are a knowledgeable assistant specializing in AI, RAG systems, and observability.

Answer the following question clearly and concisely:

{{question}}""",
    },
]


def setup_prompts():
    print(f"Connecting to ObTrac at {API} ...")

    # Check backend is up
    try:
        requests.get(f"{API}/prompts", timeout=5)
    except Exception:
        print(f"ERROR: Cannot reach {API}. Is the backend running?")
        sys.exit(1)

    # Fetch existing prompts
    existing = set()
    try:
        resp = requests.get(f"{API}/prompts", timeout=5)
        for p in resp.json().get("prompts", []):
            existing.add(p["name"])
    except Exception:
        pass

    created, skipped = [], []

    for p in PROMPTS:
        if p["name"] in existing:
            skipped.append(p["name"])
            print(f"  SKIP  {p['name']} (already exists)")
            continue

        resp = requests.post(
            f"{API}/prompts",
            json={**p, "created_by": "setup_script"},
            timeout=10,
        )
        if resp.ok:
            created.append(p["name"])
            print(f"  CREATE {p['name']}")
        else:
            print(f"  ERROR  {p['name']}: {resp.text[:200]}")

    print(f"\nDone. Created: {len(created)} | Skipped (already exist): {len(skipped)}")
    print("\nPrompts in registry:", ", ".join(created + list(skipped)))
    print("\nYou can now run the Streamlit app:")
    print("  streamlit run demos/langgraph_streamlit_rag/streamlit_main_app.py")


if __name__ == "__main__":
    setup_prompts()
