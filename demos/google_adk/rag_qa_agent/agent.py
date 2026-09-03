"""
RAG Q&A Agent — ObTrac + Google ADK

Capabilities:
  - Document retrieval from an in-memory store (simulated vector search)
  - Web search fallback when docs don't cover the topic
  - Multi-turn conversation via ADK sessions

ObTrac integration:
  - before/after_agent_callback → root Trace per turn (with session continuity)
  - @trace on rag_lookup → retrieval Span (context auto-collected from this span)
  - @trace on web_search → tool_call Span
  - session_id from ADK session auto-detected — Sessions page shows conversation

Run with:
    adk web demos/google_adk/rag_qa_agent
    # then open http://localhost:8000

Or run both agents together:
    cd demos/google_adk && adk web .
"""

import os
import sys

_GADK_ROOT = os.path.dirname(os.path.dirname(__file__))
_PROJECT_ROOT = os.path.dirname(_GADK_ROOT)
for _p in (_GADK_ROOT, _PROJECT_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from dotenv import load_dotenv
import litellm
litellm.drop_params = True

from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm

from obtrac_sdk import obtrac_config
from tools.rag_tool import rag_lookup
from tools.search_tool import web_search
from callbacks import (
    obtrac_before_agent,
    obtrac_after_agent,
    obtrac_before_model,
    obtrac_after_model,
    obtrac_before_tool,
    obtrac_after_tool,
)

load_dotenv()

obtrac_config(
    project="adk-rag-qa-agent",
    backend_url="http://localhost:8100",
    user="satyam",
    auto_eval=False,
)

_model = LiteLlm(
    model=f"azure/{os.getenv('AZURE_OPENAI_DEPLOYMENT', 'gpt-4o')}",
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_base=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
)

root_agent = Agent(
    name="rag_qa_agent",
    model=_model,
    description="A RAG-powered Q&A agent that retrieves documents before answering.",
    instruction="""You are a knowledgeable Q&A assistant with access to a document store.

You have access to:
- rag_lookup: retrieve relevant document chunks from the knowledge base.
  Always call this FIRST before answering any factual question.
- web_search: fall back to web search if rag_lookup doesn't return useful results.

Workflow for every question:
1. Call rag_lookup with the user's question.
2. If the chunks are relevant, answer using ONLY that information.
3. If chunks are not relevant, call web_search and answer from those results.
4. Always be concise and cite your sources.

Topics in the knowledge base: ObTrac, RAG, LLMs, Google ADK.""",
    tools=[rag_lookup, web_search],
    before_agent_callback=obtrac_before_agent,
    after_agent_callback=obtrac_after_agent,
    before_model_callback=obtrac_before_model,
    after_model_callback=obtrac_after_model,
    before_tool_callback=obtrac_before_tool,
    after_tool_callback=obtrac_after_tool,
)
