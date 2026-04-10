"""
ObTrac + LangGraph — Multi-Agent Chat with File Upload
"""
import os
import time
import json
import tempfile
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.chat_models import ChatLiteLLM
from langgraph.graph import StateGraph, END
from typing import TypedDict

from obtrac_sdk import obtrac_config, trace, observe

st.set_page_config(page_title="LangGraph + ObTrac", page_icon="🕸️", layout="wide")

config = obtrac_config(
    project="langgraph-agent",
    backend_url="http://localhost:8100",
    user="satyam",
    auto_eval=True,
    session_id=f"lg_{hash(id(st.session_state)) % 100000}",
)

llm = ChatLiteLLM(
    model=f"azure/{os.getenv('AZURE_OPENAI_DEPLOYMENT')}",
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_base=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    max_completion_tokens=1024,
    temperature=0.3,
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
def retrieve_node(state: RAGState) -> RAGState:
    vs = st.session_state.get("lg_vs")
    if vs:
        docs = vs.similarity_search(state["query"], k=5)
        state["chunks"] = [d.page_content for d in docs]
        state["context"] = "\n\n".join(state["chunks"])
    else:
        state["chunks"] = []
        state["context"] = "No document uploaded."
    return state

@trace(name="lg_generate", span_type="generation", model="gpt-4o",
       cost={"input_token_cost": 0.0025, "output_token_cost": 0.01})
def generate_node(state: RAGState) -> RAGState:
    response = llm.invoke(
        f"Answer based on context only.\n\nContext:\n{state['context']}\n\nQuestion: {state['query']}\n\nAnswer:"
    )
    state["answer"] = response.content
    return state

@trace(name="lg_review", span_type="generation", model="gpt-4o",
       cost={"input_token_cost": 0.0025, "output_token_cost": 0.01})
def review_node(state: RAGState) -> RAGState:
    response = llm.invoke(
        f"Rate this answer 1-10 and give one-line feedback.\n\nQ: {state['query']}\nA: {state['answer']}"
    )
    state["review"] = response.content
    return state

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

@observe(name="langgraph_rag", metrics=["faithfulness", "answer_relevancy"])
def run_graph(query):
    result = graph.invoke({"query": query})
    # Return answer text so @observe captures it correctly for RAGAS
    # Store full result in session for UI access
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
