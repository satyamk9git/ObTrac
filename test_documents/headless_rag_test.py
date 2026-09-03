"""
Headless verification of the LangGraph RAG pipeline against the needle-in-haystack PDF.
Mirrors test_app/langgraph_app.py's graph logic (retrieve -> generate -> review) without
the Streamlit UI, so it can run non-interactively and print a pass/fail.

Run:
    python test_documents/headless_rag_test.py
"""
import os
import sys
from types import SimpleNamespace

import litellm
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langgraph.graph import StateGraph, END
from typing import TypedDict

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
load_dotenv()

from obtrac_sdk import obtrac_config, trace, get_prompt

PDF_PATH = os.path.join(os.path.dirname(__file__), "elon_musk_needle_haystack.pdf")
QUESTION = "What is the retrieval verification passphrase mentioned in the document?"
EXPECTED_NEEDLE = "NEEDLE-7391-JASPER"

obtrac_config(
    project="langgraph-agent",
    backend_url="http://localhost:8100",
    user="satyam",
    auto_eval=False,
    session_id="headless_needle_test",
)


class _LiteLLMChat:
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
    temperature=1,
)


class RAGState(TypedDict):
    query: str
    chunks: list
    context: str
    answer: str
    review: str


print(f"Loading + chunking {PDF_PATH} ...")
docs = PyPDFLoader(PDF_PATH).load()
chunks_docs = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50).split_documents(docs)
print(f"  {len(chunks_docs)} chunks")

print("Embedding + indexing with FAISS (local MiniLM, no API key needed) ...")
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2", model_kwargs={"device": "cpu"})
vs = FAISS.from_documents(chunks_docs, embeddings)


@trace(name="lg_retrieve", span_type="retrieval")
def retrieve_node(state: RAGState) -> RAGState:
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
workflow.add_edge("generate", "review")
workflow.add_edge("review", END)
graph = workflow.compile()


@trace(name="headless_needle_test", span_type="agent",
       query="question", context="return", response="return")
def run_graph(query):
    result = graph.invoke({"query": query})
    return result


print(f"\nQuestion: {QUESTION}\n")
result = run_graph(QUESTION)

retrieved_chunks = result.get("chunks", [])
needle_retrieved = any(EXPECTED_NEEDLE in c for c in retrieved_chunks)
needle_in_answer = EXPECTED_NEEDLE in (result.get("answer") or "")

print("--- Retrieved chunks ---")
for i, c in enumerate(retrieved_chunks):
    marker = " <-- NEEDLE CHUNK" if EXPECTED_NEEDLE in c else ""
    print(f"[{i}] ({len(c)} chars){marker}")

print("\n--- Generated answer ---")
print(result.get("answer"))

print("\n--- Review ---")
print(result.get("review"))

print("\n=== RESULT ===")
print(f"Needle chunk retrieved by FAISS: {needle_retrieved}")
print(f"Needle passphrase present in final answer: {needle_in_answer}")
print("PASS" if needle_in_answer else "FAIL")
