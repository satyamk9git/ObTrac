"""
ObTrac + LangGraph — DELIBERATELY BAD RAG demo app.

Purpose: exercise ObTrac's dashboard with genuinely low RAGAS-style scores
(faithfulness, answer_relevancy, context_precision, context_recall,
answer_correctness, answer_similarity) — for real, not faked.

Design of the badness (see test_app/langgraph_app.py for the GOOD reference
pipeline this deliberately inverts):
  1. Narrow corpus (Solstice Robotics Q3-2026-ONLY earnings summary) +
     questions about adjacent-but-uncovered topics (Q1 2026, YoY comparisons,
     full-year guidance, competitor names, Q2 2026 figures) — none of which
     appear anywhere in the corpus. This forces the retriever to return the
     closest-but-wrong chunks with false confidence.
  2. Bad chunking: chunk_size=2000, chunk_overlap=0 — large chunks with no
     overlap, so facts get diluted inside chunks full of unrelated
     surrounding text (financial figures next to risk-factor boilerplate,
     etc.) and no fact is ever safely straddled across a chunk boundary.
  3. Weak retrieval: k=2 — too few candidates to have a good shot at
     anything useful when the corpus is already a near-miss for the query.
  4. A generation prompt ("bad_rag_answer") that explicitly instructs the
     model to hallucinate: fill gaps with general knowledge, never say
     "I don't know", always give a confident, definitive answer. This is
     the most reliable way to tank faithfulness specifically.
  5. A rubber-stamp review node ("bad_review") that always says "Looks
     good" and never catches or flags the bad answers.
  6. Each test question carries an invented (but never-retrieved) ground
     truth so context_recall / answer_correctness / answer_similarity all
     have something concrete to fail against too.

Run directly as a script (not Streamlit) for testability:
    source .venv/bin/activate
    python test_app/bad_langgraph_app.py
"""
import os
import sys
import time
import json
from types import SimpleNamespace
from typing import TypedDict

import litellm
from dotenv import load_dotenv

# Allow running as a standalone script from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langgraph.graph import StateGraph, END

from obtrac_sdk import obtrac_config, trace, get_prompt

RAG_EVAL_METRICS = [
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
    "answer_correctness",
    "answer_similarity",
]

CORPUS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "test_documents",
    "solstice_q3_2026_earnings.txt",
)

SESSION_ID = f"bad_rag_{int(time.time())}"

config = obtrac_config(
    project="bad-rag-demo",
    backend_url="http://localhost:8100",
    user="satyam",
    auto_eval=True,
    default_metrics=RAG_EVAL_METRICS,
    session_id=SESSION_ID,
)


class _LiteLLMChat:
    """Minimal ChatLiteLLM replacement — langchain_community 0.4.x removed
    ChatLiteLLM entirely, so call litellm directly and keep the same
    `.invoke(text) -> obj.content` interface the rest of this file expects."""

    def __init__(self, model, api_key, max_tokens, temperature):
        self.model = model
        self.api_key = api_key
        self.max_tokens = max_tokens
        self.temperature = temperature

    def invoke(self, prompt_text: str):
        resp = litellm.completion(
            model=self.model,
            api_key=self.api_key,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[{"role": "user", "content": prompt_text}],
        )
        return SimpleNamespace(content=resp.choices[0].message.content)


llm = _LiteLLMChat(
    model="anthropic/claude-sonnet-5",
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    max_tokens=1024,
    # Claude Sonnet 5 runs extended thinking by default and rejects any
    # temperature other than 1 while thinking is active. Never pass top_p.
    temperature=1,
)

_embeddings = None


def get_embeddings():
    global _embeddings
    if _embeddings is None:
        _embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={"device": "cpu"},
        )
    return _embeddings


def build_bad_index(path: str):
    """Deliberately bad chunking: large chunks, zero overlap."""
    loader = TextLoader(path, encoding="utf-8")
    docs = loader.load()
    chunks = RecursiveCharacterTextSplitter(
        chunk_size=2000, chunk_overlap=0
    ).split_documents(docs)
    vs = FAISS.from_documents(chunks, get_embeddings())
    return vs, len(chunks)


# --- Graph State ---
class BadRAGState(TypedDict):
    query: str
    chunks: list
    context: str
    answer: str
    review: str


VECTORSTORE = None  # populated in main()


# --- Graph Nodes (each traced) ---
@trace(name="bad_retrieve", span_type="retrieval")
def retrieve_node(state: BadRAGState) -> dict:
    # Weak retrieval: k=2 only — too few candidates to have a good shot at
    # the right chunk when the corpus is already a near-miss for the query.
    docs = VECTORSTORE.similarity_search(state["query"], k=2)
    chunks = [d.page_content for d in docs]
    context = "\n\n".join(chunks)
    # Return only the keys this node updates — LangGraph merges partial
    # state updates; returning the whole state pollutes ObTrac's
    # auto-backfilled trace context with JSON noise.
    return {"chunks": chunks, "context": context}


@trace(
    name="bad_generate",
    span_type="generation",
    model="claude-sonnet-5",
    cost={"input_token_cost": 0.002, "output_token_cost": 0.01},
)
def generate_node(state: BadRAGState) -> dict:
    prompt = get_prompt("bad_rag_answer")
    rendered = prompt.render(context=state["context"], question=state["query"])
    response = llm.invoke(rendered)
    return {"answer": response.content}


@trace(
    name="bad_review",
    span_type="generation",
    model="claude-sonnet-5",
    cost={"input_token_cost": 0.002, "output_token_cost": 0.01},
)
def review_node(state: BadRAGState) -> dict:
    # Rubber-stamp reviewer — always approves, never catches the bad answer.
    prompt = get_prompt("bad_review")
    rendered = prompt.render(question=state["query"], answer=state["answer"])
    response = llm.invoke(rendered)
    return {"review": response.content}


# --- Build Graph ---
workflow = StateGraph(BadRAGState)
workflow.add_node("retrieve", retrieve_node)
workflow.add_node("generate", generate_node)
workflow.add_node("review", review_node)
workflow.set_entry_point("retrieve")
workflow.add_edge("retrieve", "generate")
workflow.add_edge("generate", "review")
workflow.add_edge("review", END)
graph = workflow.compile()


@trace(
    name="bad_rag_pipeline",
    span_type="agent",
    response="return",
    ground_truth="ground_truth",
    metrics=RAG_EVAL_METRICS,
)
def run_pipeline(query: str, ground_truth: str = None) -> str:
    result = graph.invoke({"query": query})
    return result.get("answer", str(result))


# --- Test battery: plausible-but-NOT-covered questions -----------------
# The corpus (test_documents/solstice_q3_2026_earnings.txt) covers ONLY
# Q3 2026 (Jul-Sep 2026) in isolation: no Q1/Q2 2026 figures, no prior-year
# (2025) figures, no full-year totals, no competitor names, no YoY deltas.
# Each question below is topically adjacent (same company, same general
# subject) but the answer is never in the corpus — forcing the retriever to
# surface the closest-but-wrong Q3-only chunks, and the hallucination-primed
# generation prompt to confidently fabricate an answer instead of saying
# "not disclosed". ground_truth is an invented gold answer that is never
# retrievable from this corpus either, so context_recall / answer_correctness
# / answer_similarity all have something concrete to fail against.
TEST_QUESTIONS = [
    {
        "query": "What was Solstice Robotics' revenue growth in Q1 2026 compared to Q4 2025?",
        "ground_truth": "Q1 2026 revenue was $46.2 million, up 9% from $42.4 million in Q4 2025.",
    },
    {
        "query": "How does Solstice's Q3 2026 customer churn rate compare to the same quarter last year (Q3 2025)?",
        "ground_truth": "Q3 2026 churn was 3.2%, down from 5.1% in Q3 2025, an improvement of 1.9 percentage points.",
    },
    {
        "query": "What is Solstice Robotics' full-year 2026 revenue guidance?",
        "ground_truth": "Full-year 2026 revenue guidance is approximately $225 million to $230 million.",
    },
    {
        "query": "Which competitor did Solstice lose the most warehouse deployment market share to in Q3 2026?",
        "ground_truth": "Solstice lost the most market share to Kinetix Automation, a rival warehouse-robotics vendor, during Q3 2026.",
    },
    {
        "query": "How many enterprise customers did Solstice Robotics add in Q2 2026?",
        "ground_truth": "Solstice added 14 new enterprise customers in Q2 2026.",
    },
]


def main():
    global VECTORSTORE
    print(f"Loading corpus from {CORPUS_PATH} ...")
    VECTORSTORE, n_chunks = build_bad_index(CORPUS_PATH)
    print(f"Indexed {n_chunks} chunks (chunk_size=2000, chunk_overlap=0, k=2 at query time)")
    print(f"Project: bad-rag-demo | session_id={SESSION_ID}\n")

    trace_ids = []
    for i, item in enumerate(TEST_QUESTIONS, start=1):
        q = item["query"]
        gt = item["ground_truth"]
        print(f"[{i}/{len(TEST_QUESTIONS)}] Q: {q}")
        t0 = time.time()
        try:
            answer = run_pipeline(q, ground_truth=gt)
            elapsed = time.time() - t0
            print(f"    A ({elapsed:.1f}s): {answer[:300]}")
        except Exception as e:
            print(f"    ERROR: {type(e).__name__}: {e}")
        print()
        time.sleep(2)  # small gap between root traces

    wait_s = 10 * len(TEST_QUESTIONS)
    print(f"Done sending {len(TEST_QUESTIONS)} traces. Waiting {wait_s}s for background auto-eval to land...")
    time.sleep(wait_s)
    print("Now check:")
    print("  curl 'http://localhost:8100/api/v1/traces?project=bad-rag-demo&limit=10'")
    print("  curl 'http://localhost:8100/api/v1/metrics/summary?project=bad-rag-demo'")


if __name__ == "__main__":
    main()
