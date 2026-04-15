"""
Web search tool for Google ADK agents.

ObTrac integration:
- @trace wraps the function → becomes a child span inside the agent's root trace
- session_id is auto-detected from ToolContext.invocation_context.session.id
  (added to _extract_session_id in v0.6.7)
"""

import random
from google.adk.tools import ToolContext
from obtrac_sdk import trace

_KNOWLEDGE = {
    "rag": [
        "RAG (Retrieval-Augmented Generation) grounds LLM responses in retrieved documents.",
        "RAG reduces hallucinations by 40-60% compared to pure generation.",
        "Key components: chunker, embedder, vector store, retriever, generator.",
        "Popular RAG frameworks: LangChain, LlamaIndex, Haystack.",
    ],
    "observability": [
        "LLM observability tracks latency, cost, token usage, and eval scores per request.",
        "Key signals: TTFT, throughput, faithfulness, answer relevancy, context precision.",
        "Tools: ObTrac, LangSmith, Helicone, Phoenix, Trulens.",
        "Tracing gives a span-by-span breakdown of each pipeline step.",
    ],
    "llm": [
        "LLMs are transformer-based neural networks trained on internet-scale text.",
        "Leading models: GPT-4o (OpenAI), Claude 3.5 (Anthropic), Gemini 2.0 (Google).",
        "Fine-tuning adapts a model to a domain; RAG gives it up-to-date knowledge.",
        "Inference cost: ~$0.002–$0.015 per 1K tokens depending on model/provider.",
    ],
    "google adk": [
        "Google ADK (Agent Development Kit) is Google's open-source agent framework.",
        "ADK supports multi-agent hierarchies, tool use, and streaming.",
        "adk web provides a local UI to test agents interactively.",
        "ADK integrates with Vertex AI, LiteLLM, and LangChain.",
    ],
    "vector database": [
        "Vector databases store embeddings and support approximate nearest-neighbor search.",
        "Popular options: Pinecone, Weaviate, Qdrant, FAISS, ChromaDB.",
        "ANN algorithms: HNSW (most popular), IVF, LSH.",
        "Typical recall@10 with HNSW: 95-99% at millisecond latency.",
    ],
    "default": [
        "Search results are simulated for demo purposes.",
        "In production, connect a real API (Tavily, Bing, SerpAPI).",
        "ObTrac traces the tool call latency regardless of the backend.",
    ],
}


@trace(name="web_search", span_type="tool_call")
def web_search(query: str, tool_context: ToolContext) -> dict:
    """
    Search the web for information about a topic.

    Args:
        query: The search query.
        tool_context: Injected by ADK — carries session info auto-detected by ObTrac.

    Returns:
        dict with 'results' key containing search result strings.
    """
    q = query.lower()
    facts = _KNOWLEDGE["default"]
    for key in _KNOWLEDGE:
        if key in q:
            facts = _KNOWLEDGE[key]
            break

    selected = random.sample(facts, min(3, len(facts)))
    return {
        "query": query,
        "results": selected,
        "source": "simulated (connect real API in production)",
    }
