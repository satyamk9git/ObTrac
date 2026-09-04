"""
ObTrac + LangGraph — Multi-Agent Chat with File Upload
"""
import os
import time
import json
import tempfile
from types import SimpleNamespace
import litellm
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langgraph.graph import StateGraph, END
from typing import TypedDict

from obtrac_sdk import obtrac_config, trace, get_prompt

st.set_page_config(page_title="LangGraph + ObTrac", page_icon="🕸️", layout="wide")

RAG_EVAL_METRICS = [
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
    "answer_correctness",
]

config = obtrac_config(
    project="langgraph-agent",
    backend_url="http://localhost:8100",
    user="satyam",
    auto_eval=True,
    default_metrics=RAG_EVAL_METRICS,
    session_id=f"lg_{hash(id(st.session_state)) % 100000}",
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
    # temperature other than 1 while thinking is active.
    temperature=1,
)

@st.cache_resource
def get_embeddings():
    return HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2", model_kwargs={"device": "cpu"})

def process_file(uploaded_file):
    suffix = os.path.splitext(uploaded_file.name)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = tmp.name
    loader = PyPDFLoader(tmp_path) if suffix == ".pdf" else TextLoader(tmp_path, encoding="utf-8")
    docs = loader.load()
    os.unlink(tmp_path)
    chunks = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50).split_documents(docs)
    return FAISS.from_documents(chunks, get_embeddings()), len(chunks)

# --- Graph State ---
class RAGState(TypedDict):
    query: str
    chunks: list
    context: str
    answer: str
    review: str

# --- Graph Nodes (each traced) ---
@trace(name="lg_retrieve", span_type="retrieval")
def retrieve_node(state: RAGState) -> dict:
    vs = st.session_state.get("lg_vs")
    if vs:
        docs = vs.similarity_search(state["query"], k=5)
        chunks = [d.page_content for d in docs]
        context = "\n\n".join(chunks)
    else:
        chunks = []
        context = "No document uploaded."
    # Return only the keys this node updates (LangGraph merges partial state
    # updates) — returning the whole `state` dict here previously meant the
    # retrieval span's output (and therefore the auto-backfilled trace
    # context used by RAGAS scoring) was polluted with the raw query and
    # duplicated chunk list instead of just the retrieved text.
    return {"chunks": chunks, "context": context}

@trace(name="lg_generate", span_type="generation", model="claude-sonnet-5",
       cost={"input_token_cost": 0.002, "output_token_cost": 0.01})
def generate_node(state: RAGState) -> dict:
    # Fetch the active version of "rag_answer" prompt from ObTrac registry
    prompt = get_prompt("rag_answer")
    rendered = prompt.render(context=state["context"], question=state["query"])
    response = llm.invoke(rendered)
    return {"answer": response.content}

@trace(name="lg_review", span_type="generation", model="claude-sonnet-5",
       cost={"input_token_cost": 0.002, "output_token_cost": 0.01})
def review_node(state: RAGState) -> dict:
    # Fetch the active version of "review_prompt" from ObTrac registry
    prompt = get_prompt("review_prompt")
    rendered = prompt.render(question=state["query"], answer=state["answer"])
    response = llm.invoke(rendered)
    return {"review": response.content}

# --- Build Graph ---
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
    # Return the clean answer text so @trace's default root-mode field
    # mapping (return value -> trace.answer) captures it without noise.
    # Store the full result in session for UI access.
    st.session_state._lg_last_result = result
    return result.get("answer", str(result))

# --- UI ---
st.title("🕸️ LangGraph RAG + ObTrac")
st.caption("Retrieve → Generate → Review pipeline. All traced.")

uploaded = st.file_uploader("Upload PDF/TXT", type=["pdf", "txt"], key="lg_upload")
if uploaded:
    if "lg_vs" not in st.session_state or st.session_state.get("lg_file") != uploaded.name:
        with st.spinner("Indexing..."):
            vs, n = process_file(uploaded)
            st.session_state.lg_vs = vs
            st.session_state.lg_file = uploaded.name
        st.success(f"{uploaded.name} — {n} chunks indexed")

    if "lg_msgs" not in st.session_state:
        st.session_state.lg_msgs = []
    for m in st.session_state.lg_msgs:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            if "review" in m:
                st.caption(f"Review: {m['review']}")

    if prompt := st.chat_input("Ask about your document"):
        st.session_state.lg_msgs.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Running graph: Retrieve → Generate → Review..."):
                t0 = time.time()
                answer = run_graph(prompt)
                full_result = st.session_state.get("_lg_last_result", {})
                review = full_result.get("review", "")
                elapsed = time.time() - t0
                st.markdown(answer)
                if review:
                    st.caption(f"Review: {review}")
                st.caption(f"{elapsed:.1f}s | Auto-eval running in background | [Dashboard](http://localhost:3100)")
                st.session_state.lg_msgs.append({"role": "assistant", "content": answer, "review": review})
else:
    st.info("Upload a PDF or TXT to start chatting")
