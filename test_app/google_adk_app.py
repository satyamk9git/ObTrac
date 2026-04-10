"""
ObTrac + Google ADK Style — Agent Chat with Tools + File Upload
(Uses LiteLLM with Azure OpenAI as the LLM backend)
"""
import os
import json
import time
import tempfile
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from litellm import completion

from obtrac_sdk import obtrac_config, trace, observe

st.set_page_config(page_title="ADK Agent + ObTrac", page_icon="🤖", layout="wide")

config = obtrac_config(
    project="google-adk-agent",
    backend_url="http://localhost:8100",
    user="satyam",
    session_id=f"adk_{hash(id(st.session_state)) % 100000}",
)

def call_llm(messages, system=None):
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.extend(messages)
    return completion(
        model=f"azure/{os.getenv('AZURE_OPENAI_DEPLOYMENT')}",
        messages=msgs,
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_base=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        max_completion_tokens=1024,
        temperature=0.3,
    ).choices[0].message.content

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

# --- Tools ---
@trace(name="tool_search_docs", span_type="retrieval")
def tool_search(query):
    vs = st.session_state.get("adk_vs")
    if not vs:
        return "No document uploaded."
    docs = vs.similarity_search(query, k=3)
    return "\n---\n".join([d.page_content for d in docs])

@trace(name="tool_calculate", span_type="tool_call")
def tool_calc(expr):
    try:
        allowed = set("0123456789+-*/.() ")
        if all(c in allowed for c in expr):
            return str(eval(expr))
        return "Invalid expression"
    except Exception as e:
        return f"Error: {e}"

@trace(name="tool_summarize", span_type="generation", model="gpt-4o",
       cost={"input_token_cost": 0.0025, "output_token_cost": 0.01})
def tool_summarize(text):
    return call_llm([{"role": "user", "content": f"Summarize:\n\n{text}"}], "Be concise.")

TOOLS = {"search_docs": tool_search, "calculate": tool_calc, "summarize": tool_summarize}

# --- Agent ---
@trace(name="agent_decide", span_type="generation", model="gpt-4o",
       cost={"input_token_cost": 0.0025, "output_token_cost": 0.01})
def agent_decide(query, history):
    hist = "\n".join(history[-5:]) if history else "None"
    resp = call_llm([{"role": "user", "content": f"""Tools: search_docs, calculate, summarize
History: {hist}
Query: {query}
Reply JSON: {{"action":"tool_name","input":"..."}} or {{"action":"final","answer":"..."}}"""}],
        "Reply only JSON.")
    try:
        t = resp.strip()
        if t.startswith("```"):
            t = t.split("```")[1].lstrip("json\n")
        return json.loads(t)
    except:
        return {"action": "final", "answer": resp}

@observe(name="adk_agent_pipeline")
def run_agent(query, max_steps=4):
    history = []
    for i in range(max_steps):
        decision = agent_decide(query, history)
        if decision.get("action") == "final":
            return decision.get("answer", ""), history
        tool = TOOLS.get(decision.get("action", ""))
        if tool:
            result = tool(decision.get("input", ""))
            history.append(f"{decision['action']}({decision.get('input','')[:50]}) → {str(result)[:100]}")
        else:
            return decision.get("answer", f"Unknown tool: {decision.get('action')}"), history
    return call_llm([{"role": "user", "content": f"Steps:\n{chr(10).join(history)}\n\nAnswer: {query}"}]), history

# --- UI ---
st.title("🤖 ADK Agent + ObTrac")
st.caption("Agent with tools: search_docs, calculate, summarize. All traced.")

uploaded = st.file_uploader("Upload PDF/TXT", type=["pdf", "txt"], key="adk_upload")
if uploaded:
    if "adk_vs" not in st.session_state or st.session_state.get("adk_file") != uploaded.name:
        with st.spinner("Indexing..."):
            vs, n = process_file(uploaded)
            st.session_state.adk_vs = vs
            st.session_state.adk_file = uploaded.name
        st.success(f"{uploaded.name} — {n} chunks indexed")

if "adk_msgs" not in st.session_state:
    st.session_state.adk_msgs = []
for m in st.session_state.adk_msgs:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if "steps" in m:
            with st.expander("Agent Steps"):
                for s in m["steps"]:
                    st.text(s)

if prompt := st.chat_input("Ask the agent anything..."):
    st.session_state.adk_msgs.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Agent thinking..."):
            t0 = time.time()
            answer, steps = run_agent(prompt)
            st.markdown(answer)
            if steps:
                with st.expander("Agent Steps"):
                    for s in steps:
                        st.text(s)
            st.caption(f"{time.time()-t0:.1f}s | [Dashboard](http://localhost:3100)")
            st.session_state.adk_msgs.append({"role": "assistant", "content": answer, "steps": steps})
