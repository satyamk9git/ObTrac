"""
RAG lookup tool — simulates document retrieval for the rag_qa_agent.
In production replace the in-memory store with a real vector DB.
"""

import random
from google.adk.tools import ToolContext
from obtrac_sdk import trace

# Simulated document store: topic → chunks
_DOC_STORE = {
    "observability": [
        "ObTrac is an open-source RAG observability framework that tracks traces, spans, cost, and evaluation metrics.",
        "Traces in ObTrac contain spans representing each pipeline step: retrieval, generation, tool calls.",
        "ObTrac supports RAGAS evaluation metrics: faithfulness, answer_relevancy, context_precision, context_recall.",
        "The @trace decorator auto-detects root vs child context — no configuration needed.",
        "Sessions in ObTrac group multiple conversation turns by session_id for HITL analysis.",
    ],
    "rag": [
        "RAG combines a retrieval system with a language model to produce grounded answers.",
        "The retrieval step uses vector similarity search over embedded document chunks.",
        "Chunk size of 300-500 tokens with 50-token overlap works well for most documents.",
        "Hybrid search (dense + sparse) outperforms pure vector search on most benchmarks.",
        "Re-ranking retrieved chunks before generation improves faithfulness scores by ~15%.",
    ],
    "llm": [
        "Temperature controls randomness: 0.0 = deterministic, 1.0 = creative.",
        "Context window sizes: GPT-4o 128K tokens, Claude 3.5 200K tokens, Gemini 2.0 1M tokens.",
        "Chain-of-thought prompting improves reasoning accuracy on math and logic tasks.",
        "Tool use (function calling) lets LLMs interact with external systems reliably.",
        "Structured output with JSON mode reduces parsing errors from ~15% to <1%.",
    ],
    "google adk": [
        "Google ADK uses InvocationContext to pass session and state across agent calls.",
        "adk web provides an interactive UI for testing agents locally with real-time streaming.",
        "ADK supports multi-agent pipelines: root agents can delegate to sub-agents.",
        "Tool functions in ADK receive a ToolContext which carries session metadata.",
        "ADK callbacks (before/after agent, model, tool) enable observability hooks.",
    ],
    "default": [
        "No specific documents found. Returning general knowledge.",
        "Try asking about: observability, RAG, LLMs, or Google ADK.",
    ],
}


@trace(name="rag_lookup", span_type="retrieval")
def rag_lookup(query: str, top_k: int = 3, tool_context: ToolContext = None) -> dict:
    """
    Retrieve relevant document chunks for a query (simulated vector search).

    Args:
        query: User's question.
        top_k: Number of chunks to return (default 3).
        tool_context: Injected by ADK — session_id auto-detected by ObTrac.

    Returns:
        dict with 'chunks' list and 'source' key.
    """
    q = query.lower()
    chunks = _DOC_STORE["default"]
    for topic, docs in _DOC_STORE.items():
        if topic in q:
            chunks = docs
            break

    selected = random.sample(chunks, min(top_k, len(chunks)))
    return {
        "query": query,
        "chunks": selected,
        "chunk_count": len(selected),
        "source": "in-memory-store (replace with real vector DB)",
    }
