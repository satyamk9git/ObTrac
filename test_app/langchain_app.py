"""
ObTrac + LangChain — Simple RAG Chat with File Upload
"""
import os
import uuid
import time
import tempfile
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.chat_models import ChatLiteLLM
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from obtrac_sdk import obtrac_config, trace, observe

st.set_page_config(page_title="LangChain + ObTrac", page_icon="🦜", layout="wide")

config = obtrac_config(
    project="langchain-rag",
    backend_url="http://localhost:8100",
    user="satyam",
    session_id=f"lc_{hash(id(st.session_state)) % 100000}",
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

@trace(name="lc_retrieve", span_type="retrieval")
def retrieve(query, vectorstore, k=5):
    return vectorstore.similarity_search(query, k=k)

@trace(name="lc_generate", span_type="generation", model="gpt-4o",
       cost={"input_token_cost": 0.0025, "output_token_cost": 0.01})
def generate(query, context):
    prompt = ChatPromptTemplate.from_template(
        "Answer based ONLY on context. If not in context say so.\n\nContext:\n{context}\n\nQuestion: {question}\n\nAnswer:"
    )
    chain = prompt | llm | StrOutputParser()
    return chain.invoke({"context": context, "question": query})

@observe(name="langchain_rag")
def rag_pipeline(query, vectorstore):
    docs = retrieve(query, vectorstore)
    context = "\n\n".join([d.page_content for d in docs])
    return generate(query, context)

# --- UI ---
st.title("🦜 LangChain RAG + ObTrac")
st.caption("Upload a doc, chat with it. All traced in ObTrac.")

uploaded = st.file_uploader("Upload PDF/TXT", type=["pdf", "txt"])
if uploaded:
    if "lc_vs" not in st.session_state or st.session_state.get("lc_file") != uploaded.name:
        with st.spinner("Indexing..."):
            vs, n = process_file(uploaded)
            st.session_state.lc_vs = vs
            st.session_state.lc_file = uploaded.name
        st.success(f"{uploaded.name} — {n} chunks indexed")

    if "lc_msgs" not in st.session_state:
        st.session_state.lc_msgs = []
    for m in st.session_state.lc_msgs:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    if prompt := st.chat_input("Ask about your document"):
        st.session_state.lc_msgs.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                t0 = time.time()
                answer = rag_pipeline(prompt, st.session_state.lc_vs)
                st.markdown(answer)
                st.caption(f"{time.time()-t0:.1f}s | [Dashboard](http://localhost:3100)")
                st.session_state.lc_msgs.append({"role": "assistant", "content": answer})
else:
    st.info("Upload a PDF or TXT to start chatting")
