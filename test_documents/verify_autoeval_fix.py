"""
Verifies the langgraph_app.py fixes by running the actual graph logic with
auto_eval=True (mirroring the app's current config exactly) and checking:
  1. Auto-eval fires without any manual eval call
  2. trace.context is clean (no JSON/query pollution from the old bug)
  3. Span model attribution says claude-sonnet-5, not gpt-4o
"""
import os
import sys
import time
from types import SimpleNamespace

import litellm
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langgraph.graph import StateGraph, END
from typing import TypedDict
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
load_dotenv()

from obtrac_sdk import obtrac_config, trace, get_prompt

BACKEND = "http://localhost:8100"
PDF_PATH = os.path.join(os.path.dirname(__file__), "elon_musk_needle_haystack.pdf")

RAG_EVAL_METRICS = [
    "faithfulness", "answer_relevancy", "context_precision",
    "context_recall", "answer_correctness", "answer_similarity",
]

obtrac_config(
    project="langgraph-agent", backend_url=BACKEND, user="satyam",
    auto_eval=True, default_metrics=RAG_EVAL_METRICS,
    session_id="verify_autoeval_fix",
)


class _LiteLLMChat:
    def __init__(self, model, api_key, max_tokens, temperature):
        self.model, self.api_key, self.max_tokens, self.temperature = model, api_key, max_tokens, temperature

    def invoke(self, prompt_text: str):
        resp = litellm.completion(
            model=self.model, api_key=self.api_key,
            max_tokens=self.max_tokens, temperature=self.temperature,
            messages=[{"role": "user", "content": prompt_text}],
        )
        return SimpleNamespace(content=resp.choices[0].message.content)


llm = _LiteLLMChat(model="anthropic/claude-sonnet-5", api_key=os.getenv("ANTHROPIC_API_KEY"),
                    max_tokens=1024, temperature=1)

docs = PyPDFLoader(PDF_PATH).load()
chunks_docs = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50).split_documents(docs)
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2", model_kwargs={"device": "cpu"})
vs = FAISS.from_documents(chunks_docs, embeddings)


class RAGState(TypedDict):
    query: str
    chunks: list
    context: str
    answer: str
    review: str


@trace(name="lg_retrieve", span_type="retrieval")
def retrieve_node(state: RAGState) -> dict:
    results = vs.similarity_search(state["query"], k=5)
    chunks = [d.page_content for d in results]
    context = "\n\n".join(chunks)
    return {"chunks": chunks, "context": context}


@trace(name="lg_generate", span_type="generation", model="claude-sonnet-5",
       cost={"input_token_cost": 0.002, "output_token_cost": 0.01})
def generate_node(state: RAGState) -> dict:
    prompt = get_prompt("rag_answer")
    rendered = prompt.render(context=state["context"], question=state["query"])
    response = llm.invoke(rendered)
    return {"answer": response.content}


@trace(name="lg_review", span_type="generation", model="claude-sonnet-5",
       cost={"input_token_cost": 0.002, "output_token_cost": 0.01})
def review_node(state: RAGState) -> dict:
    prompt = get_prompt("review_prompt")
    rendered = prompt.render(question=state["query"], answer=state["answer"])
    response = llm.invoke(rendered)
    return {"review": response.content}


workflow = StateGraph(RAGState)
workflow.add_node("retrieve", retrieve_node)
workflow.add_node("generate", generate_node)
workflow.add_node("review", review_node)
workflow.set_entry_point("retrieve")
workflow.add_edge("retrieve", "generate")
workflow.add_edge("generate", "review")
workflow.add_edge("review", END)
graph = workflow.compile()


@trace(name="langgraph_rag", span_type="agent", metrics=RAG_EVAL_METRICS)
def run_graph(query):
    result = graph.invoke({"query": query})
    return result.get("answer", str(result))


print("Running a real query through the FIXED pipeline (auto_eval=True)...")
question = "What year did Musk become Tesla's CEO and who founded the company?"
answer = run_graph(question)
print(f"Answer: {answer}\n")

print("Waiting for the background trace POST + auto-eval to land...")
time.sleep(8)

r = requests.get(f"{BACKEND}/api/v1/traces", params={"project": "langgraph-agent", "limit": 1})
trace_summary = r.json()["traces"][0]
trace_id = trace_summary["trace_id"]
print(f"Trace: {trace_id}")

full = requests.get(f"{BACKEND}/api/v1/traces/{trace_id}").json()

print("\n=== CHECK 1: auto-eval fired without manual call ===")
print("metrics:", full["metrics"])
assert full["metrics"], "FAIL: no metrics were auto-populated"
print("PASS — metrics auto-populated")

print("\n=== CHECK 2: context is clean (no JSON pollution) ===")
ctx = full["context"]
print(f"context length: {len(ctx)} chars")
print(f"context preview: {ctx[:200]!r}")
is_json_polluted = ctx.strip().startswith("{") and '"query"' in ctx
print("FAIL — still JSON-polluted" if is_json_polluted else "PASS — no JSON/query pollution")

print("\n=== CHECK 3: model attribution ===")
for s in full["spans"]:
    if s["span_type"] == "generation":
        print(f"  span '{s['name']}' model = {s['model']!r}")
        assert s["model"] == "claude-sonnet-5", f"FAIL: expected claude-sonnet-5, got {s['model']}"
print("PASS — all generation spans correctly attributed to claude-sonnet-5")

print("\n=== Full metrics ===")
for k, v in full["metrics"].items():
    print(f"  {k}: {v}")
