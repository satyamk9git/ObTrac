"""
ObTrac Test App — Tool library.

Each tool is decorated with @trace so every call shows up as a span in
the ObTrac dashboard.  session_id is accepted as a kwarg on every tool
so ObTrac auto-groups calls from the same conversation into one Session.
"""

import ast
import math
import operator
import random
import re
from datetime import datetime

from obtrac_sdk import trace

# ---------------------------------------------------------------------------
# Safe calculator — no eval() on arbitrary code
# ---------------------------------------------------------------------------

_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}

def _safe_eval(node):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.BinOp):
        op = _SAFE_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
        return op(_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp):
        op = _SAFE_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported unary op: {type(node.op).__name__}")
        return op(_safe_eval(node.operand))
    if isinstance(node, ast.Call):
        func_name = node.func.id if isinstance(node.func, ast.Name) else None
        allowed = {"sqrt": math.sqrt, "abs": abs, "round": round,
                   "log": math.log, "sin": math.sin, "cos": math.cos,
                   "tan": math.tan, "ceil": math.ceil, "floor": math.floor}
        if func_name in allowed:
            args = [_safe_eval(a) for a in node.args]
            return allowed[func_name](*args)
    raise ValueError(f"Unsupported expression: {ast.dump(node)}")


@trace(name="calculator", span_type="tool_call")
def calculator(expression: str, session_id: str = "") -> str:
    """Safely evaluate a math expression. session_id auto-links to conversation."""
    try:
        expression = expression.replace("^", "**").replace("×", "*").replace("÷", "/")
        tree = ast.parse(expression, mode="eval")
        result = _safe_eval(tree.body)
        if isinstance(result, float) and result.is_integer():
            result = int(result)
        return f"{expression} = {result}"
    except Exception as e:
        return f"Calculator error: {e}. Try a simpler expression like '15% of 4500'."


# ---------------------------------------------------------------------------
# Date / time
# ---------------------------------------------------------------------------

@trace(name="get_datetime", span_type="tool_call")
def get_datetime(session_id: str = "") -> str:
    """Return current date and time."""
    now = datetime.now()
    return (
        f"Current date: {now.strftime('%A, %B %d, %Y')}\n"
        f"Current time: {now.strftime('%I:%M %p')}\n"
        f"Week number: {now.isocalendar()[1]}"
    )


# ---------------------------------------------------------------------------
# Mock web search — returns plausible-looking results without calling any API
# ---------------------------------------------------------------------------

_SEARCH_FACTS = {
    "rag": [
        "RAG (Retrieval-Augmented Generation) combines a retrieval system with a generative LLM.",
        "RAG reduces hallucinations by grounding responses in retrieved documents.",
        "Introduced by Lewis et al. (2020) from Facebook AI Research.",
        "Key steps: chunk → embed → retrieve → generate.",
    ],
    "llm": [
        "Large Language Models (LLMs) are neural networks trained on massive text corpora.",
        "GPT-4, Claude, and Gemini are popular LLMs used in production.",
        "LLMs use the transformer architecture introduced in 'Attention is All You Need' (2017).",
        "Fine-tuning adapts a pre-trained LLM to a specific domain.",
    ],
    "observability": [
        "LLM observability tracks latency, token usage, cost, and evaluation scores.",
        "Key metrics: TTFT (time to first token), total latency, cost per query.",
        "Evaluation frameworks include RAGAS, ARES, and TRULENS.",
        "Tracing provides a span-by-span view of each pipeline step.",
    ],
    "python": [
        "Python is the most popular language for AI/ML development.",
        "Key libraries: numpy, pandas, scikit-learn, PyTorch, transformers.",
        "Python 3.10+ introduced structural pattern matching.",
        "The GIL (Global Interpreter Lock) limits true multi-threading in CPython.",
    ],
    "default": [
        "Search results are simulated for demo purposes.",
        "In production, connect a real search API (Tavily, Bing, Google CSE).",
        "ObTrac traces the tool call latency regardless of the underlying API.",
    ],
}

@trace(name="web_search", span_type="tool_call")
def web_search(query: str, session_id: str = "") -> str:
    """Simulate a web search and return results (mock — no real API call)."""
    q = query.lower()
    facts = _SEARCH_FACTS.get("default")
    for key in _SEARCH_FACTS:
        if key in q:
            facts = _SEARCH_FACTS[key]
            break

    selected = random.sample(facts, min(3, len(facts)))
    results = "\n".join(f"• {f}" for f in selected)
    return f"Search results for '{query}':\n{results}"


# ---------------------------------------------------------------------------
# Text summarizer (calls LLM — shows as generation span)
# ---------------------------------------------------------------------------

@trace(name="summarize", span_type="generation")
def summarize_text(text: str, max_words: int = 60, session_id: str = "") -> str:
    """Summarize text by extracting the most informative sentences (no LLM call)."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    if len(sentences) <= 3:
        return text.strip()
    # Score: prefer sentences with numbers, named entities, or keywords
    keywords = {"key", "main", "important", "critical", "result", "conclude", "shows", "found"}
    def score(s):
        s_lower = s.lower()
        return (
            sum(1 for w in keywords if w in s_lower) +
            len(re.findall(r'\d', s)) * 0.5 +
            (1 if s == sentences[0] else 0)  # first sentence bonus
        )
    ranked = sorted(sentences, key=score, reverse=True)
    # Pick top sentences, trim to max_words
    selected = []
    word_count = 0
    for s in ranked[:4]:
        words = s.split()
        if word_count + len(words) <= max_words:
            selected.append(s)
            word_count += len(words)
    # Re-order chronologically
    selected = [s for s in sentences if s in selected]
    return " ".join(selected)


# ---------------------------------------------------------------------------
# Unit converter
# ---------------------------------------------------------------------------

_CONVERSIONS = {
    "km_to_miles": lambda x: x * 0.621371,
    "miles_to_km": lambda x: x * 1.60934,
    "kg_to_lbs": lambda x: x * 2.20462,
    "lbs_to_kg": lambda x: x / 2.20462,
    "celsius_to_fahrenheit": lambda x: x * 9/5 + 32,
    "fahrenheit_to_celsius": lambda x: (x - 32) * 5/9,
    "usd_to_inr": lambda x: x * 83.5,
    "inr_to_usd": lambda x: x / 83.5,
}

@trace(name="unit_converter", span_type="tool_call")
def unit_converter(value: float, from_unit: str, to_unit: str, session_id: str = "") -> str:
    """Convert between common units. session_id links to conversation."""
    key = f"{from_unit.lower()}_to_{to_unit.lower()}"
    if key not in _CONVERSIONS:
        available = ", ".join(k.replace("_to_", " → ") for k in _CONVERSIONS)
        return f"Conversion '{from_unit} → {to_unit}' not supported. Available: {available}"
    result = _CONVERSIONS[key](value)
    return f"{value} {from_unit} = {round(result, 4)} {to_unit}"
