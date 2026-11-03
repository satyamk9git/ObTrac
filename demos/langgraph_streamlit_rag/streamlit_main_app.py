"""
Cortexa Test App — Main Streamlit UI

Modes:
  1. Simple Chat     — direct Q&A with Azure OpenAI, traced
  2. RAG Chat        — upload PDF/TXT, retrieve + generate pipeline
  3. Multi-Tool Agent — agent with calculator, search, datetime, unit converter

All modes demonstrate:
  - @trace auto-root detection (no @observe needed)
  - session_id as kwarg → auto-detected, links turns in Sessions dashboard
  - get_prompt() from registry with inline fallback
  - Child spans visible in trace detail view
"""

import os
import sys
import tempfile
import time
import uuid
from types import SimpleNamespace

import litellm
import streamlit as st
from dotenv import load_dotenv

# Make demos/ importable when launched from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

load_dotenv()

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter

from obtrac_sdk import get_prompt, obtrac_config, trace
from demos.simple_multi_tool_agent.agent import run_agent

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Cortexa Test App",
    page_icon="🔭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Session state bootstrap
# ---------------------------------------------------------------------------
if "session_id" not in st.session_state:
    st.session_state.session_id = f"conv_{uuid.uuid4().hex[:8]}"
if "messages" not in st.session_state:
    st.session_state.messages = []
if "mode" not in st.session_state:
    st.session_state.mode = "Simple Chat"
if "total_cost" not in st.session_state:
    st.session_state.total_cost = 0.0
if "turn_count" not in st.session_state:
    st.session_state.turn_count = 0

# ---------------------------------------------------------------------------
# ObTrac config
# ---------------------------------------------------------------------------
RAG_EVAL_METRICS = [
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
    "answer_correctness",
]

cfg = obtrac_config(
    project="obtrac-test-app",
    backend_url="http://localhost:8100",
    user="satyam",
    auto_eval=True,
    default_metrics=RAG_EVAL_METRICS,
    session_id=st.session_state.session_id,
)

# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------
class _LiteLLMChat:
    """Minimal ChatLiteLLM replacement — langchain_community 0.4.x removed
    ChatLiteLLM entirely, so call litellm directly and keep the same
    `.invoke(text) -> obj.content` interface the rest of this file expects."""

    def __init__(self, model, api_key, max_tokens, temperature):
        self.model, self.api_key, self.max_tokens, self.temperature = model, api_key, max_tokens, temperature

    def invoke(self, prompt_text: str):
        resp = litellm.completion(
            model=self.model, api_key=self.api_key,
            max_tokens=self.max_tokens, temperature=self.temperature,
            messages=[{"role": "user", "content": prompt_text}],
        )
        return SimpleNamespace(content=resp.choices[0].message.content)


@st.cache_resource
def get_llm():
    return _LiteLLMChat(
        model="anthropic/claude-sonnet-5",
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        max_tokens=800,
        # Claude Sonnet 5 runs extended thinking by default and rejects any
        # temperature other than 1 while thinking is active.
        temperature=1,
    )

@st.cache_resource
def get_embeddings():
    return HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        model_kwargs={"device": "cpu"},
    )

# ---------------------------------------------------------------------------
# Prompt helpers (registry with inline fallback)
# ---------------------------------------------------------------------------
_FALLBACK = {
    "simple_chat": "You are a helpful assistant specializing in AI and ML.\n\nAnswer: {{question}}",
    "rag_answer": (
        "Answer based on this context only.\n\nContext:\n{{context}}\n\n"
        "Question: {{question}}\n\nAnswer concisely in 2-4 sentences."
    ),
    "review_prompt": (
        "Review this answer.\nQ: {{question}}\nA: {{answer}}\n"
        "One sentence starting with 'Good:' or 'Needs improvement:'."
    ),
}

def get_template(name: str) -> str:
    try:
        return get_prompt(name).template
    except Exception:
        return _FALLBACK.get(name, "Answer: {{question}}")

def render_template(template: str, **kwargs) -> str:
    result = template
    for k, v in kwargs.items():
        result = result.replace(f"{{{{{k}}}}}", str(v))
    return result

# ---------------------------------------------------------------------------
# Traced functions for each mode
# ---------------------------------------------------------------------------

@trace(name="simple_chat", span_type="generation", model="claude-sonnet-5",
       cost={"input_token_cost": 0.002, "output_token_cost": 0.01})
def simple_chat(question: str, session_id: str = "") -> str:
    """Direct Q&A — @trace creates the root trace, session_id auto-detected."""
    tpl = get_template("simple_chat")
    prompt = render_template(tpl, question=question)
    llm = get_llm()
    return llm.invoke(prompt).content


@trace(name="rag_retrieve", span_type="retrieval", context="return")
def rag_retrieve(query: str, vectorstore, k: int = 5, session_id: str = "") -> str:
    """Retrieve relevant chunks — child span inside rag_pipeline."""
    docs = vectorstore.similarity_search(query, k=k)
    return "\n\n".join(d.page_content for d in docs)


@trace(name="rag_generate", span_type="generation", model="claude-sonnet-5",
       cost={"input_token_cost": 0.002, "output_token_cost": 0.01})
def rag_generate(question: str, context: str, session_id: str = "") -> str:
    """Generate answer from context — child span inside rag_pipeline."""
    tpl = get_template("rag_answer")
    prompt = render_template(tpl, context=context, question=question)
    llm = get_llm()
    return llm.invoke(prompt).content


@trace(name="rag_review", span_type="generation", model="claude-sonnet-5",
       cost={"input_token_cost": 0.002, "output_token_cost": 0.01})
def rag_review(question: str, answer: str, session_id: str = "") -> str:
    """Review the generated answer — child span inside rag_pipeline."""
    tpl = get_template("review_prompt")
    prompt = render_template(tpl, question=question, answer=answer)
    llm = get_llm()
    return llm.invoke(prompt).content


@trace(name="rag_pipeline", span_type="agent",
       query="question", response="return")
def rag_pipeline(question: str, vectorstore, session_id: str = "") -> str:
    """Full RAG pipeline — root trace with 3 child spans (retrieve/generate/review)."""
    context = rag_retrieve(question, vectorstore, session_id=session_id)
    answer = rag_generate(question, context, session_id=session_id)
    review = rag_review(question, answer, session_id=session_id)
    # Store review for UI display
    st.session_state._last_review = review
    return answer


def process_file(uploaded_file):
    suffix = os.path.splitext(uploaded_file.name)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = tmp.name
    loader = PyPDFLoader(tmp_path) if suffix == ".pdf" else TextLoader(tmp_path, encoding="utf-8")
    docs = loader.load()
    os.unlink(tmp_path)
    chunks = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50).split_documents(docs)
    vs = FAISS.from_documents(chunks, get_embeddings())
    return vs, len(chunks)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.image("frontend/public/cortexa_logo.png", width=48)
    st.markdown("## Cortexa Test App")
    st.caption("v0.6.7 — Every call is traced")

    st.divider()

    mode = st.radio(
        "Mode",
        ["Simple Chat", "RAG Chat", "Multi-Tool Agent"],
        index=["Simple Chat", "RAG Chat", "Multi-Tool Agent"].index(st.session_state.mode),
    )
    if mode != st.session_state.mode:
        st.session_state.mode = mode
        st.session_state.messages = []
        st.rerun()

    st.divider()

    st.markdown("**Session**")
    st.code(st.session_state.session_id, language=None)
    st.caption("All turns in this browser tab share one session_id — auto-detected from the kwarg.")

    col1, col2 = st.columns(2)
    col1.metric("Turns", st.session_state.turn_count)
    col2.metric("Cost", f"${st.session_state.total_cost:.4f}")

    if st.button("New Session", use_container_width=True):
        st.session_state.session_id = f"conv_{uuid.uuid4().hex[:8]}"
        st.session_state.messages = []
        st.session_state.turn_count = 0
        st.session_state.total_cost = 0.0
        st.rerun()

    st.divider()
    st.markdown("**Links**")
    st.markdown("🔭 [Cortexa Dashboard](http://localhost:3100)")
    st.markdown("📊 [Sessions](http://localhost:3100/sessions)")
    st.markdown("💬 [Traces](http://localhost:3100/traces)")

    st.divider()
    with st.expander("Sample Questions"):
        if mode == "Simple Chat":
            st.markdown("""
**Try asking:**
- What is RAG and how does it work?
- Explain hallucinations in LLMs
- What is the difference between fine-tuning and RAG?
- What metrics should I track for LLM observability?
- Explain vector databases in simple terms
""")
        elif mode == "RAG Chat":
            st.markdown("""
**After uploading a doc, try:**
- What are the main points in this document?
- Summarize the key findings
- What does the document say about [topic]?
- Are there any risks mentioned?
- What is the conclusion?
""")
        else:
            st.markdown("""
**Try asking:**
- What is 15% of 4500?
- What day is today and what week number?
- Convert 100 USD to INR
- Search for information about RAG systems
- Calculate sqrt(144) + 2^8
- Convert 10 km to miles
- What time is it right now?
- Calculate the compound interest on 10000 at 8% for 3 years
""")

# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------
mode_icons = {"Simple Chat": "💬", "RAG Chat": "📄", "Multi-Tool Agent": "🤖"}
st.markdown(f"## {mode_icons[mode]} {mode}")

# Mode description
descriptions = {
    "Simple Chat": "Direct Q&A with Azure OpenAI. Each question creates a root trace with one generation span.",
    "RAG Chat": "Upload a PDF or TXT, then ask questions. Creates a root trace with 3 spans: retrieve → generate → review.",
    "Multi-Tool Agent": "Agent picks the right tool (calculator, search, datetime, unit converter) and answers. Creates a root trace with tool + LLM child spans.",
}
st.caption(descriptions[mode])

# RAG file uploader
if mode == "RAG Chat":
    uploaded = st.file_uploader("Upload a document", type=["pdf", "txt"])
    if uploaded:
        if st.session_state.get("rag_file") != uploaded.name:
            with st.spinner(f"Indexing {uploaded.name}..."):
                vs, n = process_file(uploaded)
                st.session_state.rag_vs = vs
                st.session_state.rag_file = uploaded.name
            st.success(f"{uploaded.name} — {n} chunks indexed and ready")
    elif "rag_vs" not in st.session_state:
        st.info("Upload a PDF or TXT file to enable RAG mode.")

# Chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("tool_used") and msg["tool_used"] != "none":
            st.caption(f"🔧 Tool: `{msg['tool_used']}` | Result: {msg.get('tool_result', '')[:120]}")
        if msg.get("review"):
            st.caption(f"🔍 Review: {msg['review']}")
        if msg.get("latency"):
            st.caption(
                f"⏱ {msg['latency']:.1f}s | "
                f"[View trace in dashboard](http://localhost:3100/traces)"
            )

# Chat input
user_input = st.chat_input(
    placeholder={
        "Simple Chat": "Ask anything about AI, RAG, LLMs...",
        "RAG Chat": "Ask about your document...",
        "Multi-Tool Agent": "Try: 'What is 15% of 4500?' or 'What day is today?'",
    }[mode]
)

if user_input:
    # Guard for RAG mode without a file
    if mode == "RAG Chat" and "rag_vs" not in st.session_state:
        st.warning("Please upload a document first.")
        st.stop()

    # Show user message
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Run the pipeline
    sid = st.session_state.session_id
    t0 = time.time()
    answer = ""
    tool_used = ""
    tool_result = ""
    review = ""
    error = None

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                if mode == "Simple Chat":
                    answer = simple_chat(user_input, session_id=sid)

                elif mode == "RAG Chat":
                    answer = rag_pipeline(user_input, st.session_state.rag_vs, session_id=sid)
                    review = st.session_state.pop("_last_review", "")

                else:  # Multi-Tool Agent
                    result = run_agent(user_input, session_id=sid)
                    answer = result["answer"]
                    tool_used = result["tool_used"]
                    tool_result = result["tool_result"]

            except Exception as e:
                error = str(e)
                answer = f"Error: {e}"

        latency = time.time() - t0
        st.markdown(answer)
        if tool_used and tool_used != "none":
            st.caption(f"🔧 Tool: `{tool_used}` | Result: {tool_result[:120]}")
        if review:
            st.caption(f"🔍 Review: {review}")
        if error:
            st.error(f"Error: {error}")
        st.caption(
            f"⏱ {latency:.1f}s | session: `{sid}` | "
            f"[View in dashboard](http://localhost:3100/traces)"
        )

    # Update session stats
    st.session_state.turn_count += 1
    st.session_state.total_cost += 0.002  # rough estimate shown in sidebar
    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "tool_used": tool_used,
        "tool_result": tool_result,
        "review": review,
        "latency": latency,
    })
    st.rerun()
