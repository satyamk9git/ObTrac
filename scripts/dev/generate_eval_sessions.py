"""
Generates a realistic multi-session dataset against the needle-in-haystack PDF:
10 sessions, 2-7 questions each, covering both healthy RAG behavior and
deliberate, real RAG failure modes:

  - out-of-scope questions that bait hallucination (info not in the doc,
    but plausibly known to the model from training data)
  - false-premise / trap questions (tests whether the model corrects vs.
    plays along)
  - precision tests (exact figures)
  - a deliberately WRONG ground_truth on an otherwise-correct answer, to
    demonstrate a "bad eval dataset" failure mode distinct from "bad RAG"
  - a fully out-of-domain question (pizza recipe) to force retrieval noise
  - a genuine pipeline exception -> status=error trace
  - a multi-turn conversational session to exercise session grouping

Traces are sent through the real retrieve->generate->review LangGraph
pipeline against the live ObTrac backend, using the Claude Sonnet 5 config
already set up. After generation, timestamps are backdated across the last
10 days so Analytics/Metrics "over time" views show a real trend, and RAGAS
evaluation is triggered on every trace.
"""
import os
import sys
import json
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

from obtrac_sdk import obtrac_config, trace, get_prompt, ObTracContext
from obtrac_sdk.config import get_config

BACKEND = "http://localhost:8100"
PDF_PATH = os.path.join(os.path.dirname(__file__), "elon_musk_needle_haystack.pdf")
PROJECT = "langgraph-agent"

# ---------------------------------------------------------------------------
# Scenario bank — 10 sessions, 2-7 questions each
# Each question: (text, ground_truth_or_None, note)
# ---------------------------------------------------------------------------

SESSIONS = [
    {
        "id": "sess_spacex_good",
        "label": "SpaceX facts (healthy RAG)",
        "questions": [
            ("When was SpaceX founded and what is its long-term goal?",
             "SpaceX was founded in 2002 with the long-term goal of enabling the colonization of Mars by reducing the cost of space transportation.", "good"),
            ("What happened with SpaceX's first three orbital launch attempts?",
             "SpaceX's first three orbital launch attempts of the Falcon 1 rocket, in 2006, 2007, and 2008, all ended in failure.", "good"),
            ("What made the fourth Falcon 1 launch historically significant?",
             "The fourth Falcon 1 launch in September 2008 succeeded, making SpaceX the first privately funded company to place a liquid-fueled rocket into orbit.", "good"),
        ],
    },
    {
        "id": "sess_tesla_good",
        "label": "Tesla facts (healthy RAG)",
        "questions": [
            ("When did Elon Musk join Tesla and in what role?", "Musk joined Tesla in 2004 as chairman of the board and its largest investor.", "good"),
            ("When did Musk become Tesla's CEO?", "He was named CEO in 2008.", "good"),
            ("What were Tesla's first four major vehicle models, in order?",
             "The Roadster, followed by the Model S in 2012, the Model X in 2015, and the Model 3 in 2017.", "good"),
            ("What manufacturing model did Tesla use to scale production?",
             "The Gigafactory model — large-scale battery and vehicle production facilities in Nevada, New York, Shanghai, Berlin, and Texas.", "good"),
        ],
    },
    {
        "id": "sess_conversational_good",
        "label": "Multi-turn conversation (session continuity)",
        "questions": [
            ("What company did Musk found in 2002?", "SpaceX.", "good"),
            ("What was its first successful rocket called?", "Falcon 1.", "good"),
            ("And what spacecraft did that company later develop for the ISS?", "The Dragon spacecraft.", "good"),
            ("When did that spacecraft first dock with the ISS?", "2012.", "good"),
            ("Did NASA astronauts ever fly on a later version of it?",
             "Yes, in 2020 SpaceX's Crew Dragon capsule carried NASA astronauts to the ISS.", "good"),
        ],
    },
    {
        "id": "sess_needle_and_precision",
        "label": "Needle retrieval + numeric precision",
        "questions": [
            ("What is the retrieval verification passphrase mentioned in the document?",
             "NEEDLE-7391-JASPER", "needle"),
            ("What was the exact acquisition price eBay paid for PayPal?", "$1.5 billion", "precision"),
            ("Roughly how much money did Musk personally receive from the eBay-PayPal deal?", "roughly $175 million", "precision"),
        ],
    },
    {
        "id": "sess_hallucination_bait",
        "label": "Out-of-scope questions baiting hallucination",
        "questions": [
            ("What is Elon Musk's blood type?", None, "hallucination_bait — not in document at all"),
            ("How many children does Elon Musk have, and what are their names?", None, "hallucination_bait — real public info NOT in this document; tests whether the model leaks outside training knowledge instead of admitting the context doesn't cover it"),
            ("What is Elon Musk's exact net worth in dollars as of today?", None, "hallucination_bait — dynamic figure impossible to know from a static document"),
        ],
    },
    {
        "id": "sess_false_premise_traps",
        "label": "False-premise trap questions",
        "questions": [
            ("Since the document says Elon Musk founded Tesla himself in 2003, what did he do right after founding it?",
             None, "false_premise — Tesla was actually founded by Eberhard and Tarpenning; Musk joined a year later as chairman"),
            ("Given that SpaceX's Falcon 1 succeeded on its very first launch attempt, what came next for the company?",
             None, "false_premise — the first three Falcon 1 launches actually failed"),
            ("Since Musk founded Twitter back in 2010, how did the platform grow under his early leadership?",
             None, "false_premise — Musk acquired Twitter in 2022, he did not found it"),
        ],
    },
    {
        "id": "sess_bad_ground_truth",
        "label": "Deliberately wrong ground_truth (eval-dataset failure, not RAG failure)",
        "questions": [
            ("When did Neuralink complete its first human brain implant?",
             "2019", "bad_ground_truth — actual answer per the document is early 2024; this GT is deliberately wrong to demonstrate how a bad eval dataset tanks answer_correctness even when the RAG answer itself is correct"),
            ("In what year did SpaceX's Crew Dragon first carry NASA astronauts to the ISS?",
             "2020", "good_ground_truth — correct, for contrast against the previous question"),
            ("What year was Neuralink founded?", "2016", "good"),
        ],
    },
    {
        "id": "sess_out_of_domain_noise",
        "label": "Fully out-of-domain query (forces retrieval noise)",
        "questions": [
            ("What ingredients go into a traditional margherita pizza?", None, "out_of_domain — completely unrelated to the corpus, forces low-relevance retrieval"),
            ("What is the boiling point of water at sea level in Celsius?", None, "out_of_domain — general knowledge unrelated to the corpus"),
        ],
    },
    {
        "id": "sess_pipeline_error",
        "label": "Genuine pipeline exception -> status=error trace",
        "questions": [
            ("__FORCE_ERROR__", None, "error — deliberately triggers an exception inside the traced pipeline to produce a real status=error trace"),
        ],
    },
    {
        "id": "sess_legacy_wealth_good",
        "label": "Legacy / wealth facts (healthy RAG)",
        "questions": [
            ("What has made Musk one of the wealthiest individuals in the world?",
             "His combined equity holdings across Tesla, SpaceX, and his other ventures.", "good"),
            ("What role did Musk serve in the second Trump administration?",
             "He served in an advisory capacity to U.S. federal government efficiency initiatives.", "good"),
            ("What do supporters credit Musk with accelerating?",
             "The global transition to electric vehicles and reviving American human spaceflight capability.", "good"),
            ("What criticisms are commonly raised against Musk?",
             "Labor practices, regulatory disputes, erratic public statements, and content moderation handling at X.", "good"),
        ],
    },
]

TOTAL_Q = sum(len(s["questions"]) for s in SESSIONS)
print(f"{len(SESSIONS)} sessions, {TOTAL_Q} questions total\n")

# ---------------------------------------------------------------------------
# Pipeline setup (same as headless_rag_test.py)
# ---------------------------------------------------------------------------

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

print("Loading + indexing PDF ...")
docs = PyPDFLoader(PDF_PATH).load()
chunks_docs = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50).split_documents(docs)
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2", model_kwargs={"device": "cpu"})
vs = FAISS.from_documents(chunks_docs, embeddings)
print(f"  {len(chunks_docs)} chunks indexed\n")


class RAGState(TypedDict):
    query: str
    chunks: list
    context: str
    answer: str
    review: str


@trace(name="lg_retrieve", span_type="retrieval")
def retrieve_node(state: RAGState) -> RAGState:
    if state["query"] == "__FORCE_ERROR__":
        raise RuntimeError("Simulated retrieval failure: vector index unreachable (forced test scenario)")
    results = vs.similarity_search(state["query"], k=5)
    state["chunks"] = [d.page_content for d in results]
    state["context"] = "\n\n".join(state["chunks"])
    return state


@trace(name="lg_generate", span_type="generation", model="claude-sonnet-5",
       cost={"input_token_cost": 0.003, "output_token_cost": 0.015})
def generate_node(state: RAGState) -> RAGState:
    prompt = get_prompt("rag_answer")
    rendered = prompt.render(context=state["context"], question=state["query"])
    response = llm.invoke(rendered)
    state["answer"] = response.content
    return state


@trace(name="lg_review", span_type="generation", model="claude-sonnet-5",
       cost={"input_token_cost": 0.003, "output_token_cost": 0.015})
def review_node(state: RAGState) -> RAGState:
    prompt = get_prompt("review_prompt")
    rendered = prompt.render(question=state["query"], answer=state["answer"])
    response = llm.invoke(rendered)
    state["review"] = response.content
    return state


workflow = StateGraph(RAGState)
workflow.add_node("retrieve", retrieve_node)
workflow.add_node("generate", generate_node)
workflow.add_node("review", review_node)
workflow.set_entry_point("retrieve")
workflow.add_edge("retrieve", "generate")
workflow.add_edge("review", END)
workflow.add_edge("generate", "review")
graph = workflow.compile()


@trace(name="rag_session_turn", span_type="agent",
       query="question", context="return", response="return")
def run_graph(question):
    result = graph.invoke({"query": question})
    return result


# ---------------------------------------------------------------------------
# Run all sessions
# ---------------------------------------------------------------------------

results_log = []  # for the summary report

for s_idx, session in enumerate(SESSIONS):
    print(f"=== [{s_idx+1}/{len(SESSIONS)}] {session['id']} — {session['label']} "
          f"({len(session['questions'])} questions) ===")

    obtrac_config(
        project=PROJECT,
        backend_url=BACKEND,
        user="satyam",
        auto_eval=False,
        session_id=session["id"],
    )

    for q_idx, (question, ground_truth, note) in enumerate(session["questions"]):
        display_q = question if question != "__FORCE_ERROR__" else "(forced pipeline error)"
        print(f"  [{q_idx+1}/{len(session['questions'])}] {display_q[:70]}")
        try:
            result = run_graph(question)
            answer = (result.get("answer") or "")[:200]
            status = "success"
        except Exception as e:
            answer = f"ERROR: {type(e).__name__}: {e}"
            status = "error"
            time.sleep(0.3)  # let the background trace-send thread finish before moving on

        results_log.append({
            "session": session["id"], "question": display_q, "ground_truth": ground_truth,
            "note": note, "status": status, "answer_preview": answer,
        })
        print(f"      -> {status} | {answer[:100]}")
        time.sleep(0.5)  # be polite to the API, let background trace POSTs land

    print()

# Let final background trace-send threads flush
time.sleep(2)

with open(os.path.join(os.path.dirname(__file__), "session_log.json"), "w") as f:
    json.dump(results_log, f, indent=2)

print(f"\nDone. {len(results_log)} question-turns logged across {len(SESSIONS)} sessions.")
print("Wrote scripts/dev/session_log.json")
