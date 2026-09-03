"""
ObTrac Test App — Multi-tool agent.

Demonstrates:
  @trace auto-root detection     — run_agent() creates the root trace
  session_id kwarg               — auto-detected by ObTrac, links all
                                   turns of the same conversation
  child spans                    — llm_call(), tool runs are child spans
  get_prompt() with fallback     — uses registry prompt if available
"""

import json
import os
import re
from types import SimpleNamespace

import litellm
from dotenv import load_dotenv

from obtrac_sdk import trace, get_prompt
from demos.simple_multi_tool_agent.tools import calculator, get_datetime, web_search, summarize_text, unit_converter

load_dotenv()

# ---------------------------------------------------------------------------
# LLM setup (Anthropic via LiteLLM)
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


def _make_llm():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("Missing ANTHROPIC_API_KEY env var")
    return _LiteLLMChat(
        model="anthropic/claude-sonnet-5",
        api_key=api_key,
        max_tokens=512,
        # Claude Sonnet 5 runs extended thinking by default and rejects any
        # temperature other than 1 while thinking is active.
        temperature=1,
    )

# ---------------------------------------------------------------------------
# Prompts — registry with inline fallback
# ---------------------------------------------------------------------------

_FALLBACK_AGENT_SYSTEM = """You are a helpful assistant with access to these tools:
- calculator: evaluate math expressions (e.g. "25% of 8000")
- get_datetime: get current date and time
- web_search: search for information on any topic
- summarize: summarize a piece of text
- unit_converter: convert between units (km/miles, kg/lbs, celsius/fahrenheit, usd/inr)
- none: answer directly without a tool

Given the user's question, respond with ONLY a JSON object:
{"tool": "<tool_name>", "input": "<what to pass to the tool>"}

Examples:
Q: What is 15% of 4500?   → {"tool": "calculator", "input": "4500 * 0.15"}
Q: What time is it?        → {"tool": "get_datetime", "input": ""}
Q: Tell me about RAG       → {"tool": "web_search", "input": "RAG retrieval augmented generation"}
Q: Convert 100 USD to INR  → {"tool": "unit_converter", "input": "100 USD INR"}
Q: What is the capital of France? → {"tool": "none", "input": ""}

Question: {{question}}"""

_FALLBACK_FINAL_ANSWER = """You are a helpful, concise assistant.

User question: {{question}}
Tool used: {{tool_name}}
Tool result: {{tool_result}}

Write a clear, natural answer. Do not mention the tool name explicitly."""

def _get_prompt_safe(name: str, fallback: str) -> str:
    """Fetch prompt template from registry; silently fall back to inline."""
    try:
        p = get_prompt(name)
        return p.template
    except Exception:
        return fallback


# ---------------------------------------------------------------------------
# Traced LLM call (child span)
# ---------------------------------------------------------------------------

@trace(name="llm_call", span_type="generation", model="claude-sonnet-5",
       cost={"input_token_cost": 0.002, "output_token_cost": 0.01})
def llm_call(prompt_text: str, session_id: str = "") -> str:
    """Single LLM call — appears as a generation span inside the agent trace."""
    llm = _make_llm()
    response = llm.invoke(prompt_text)
    return response.content


# ---------------------------------------------------------------------------
# Tool dispatcher (child span)
# ---------------------------------------------------------------------------

@trace(name="tool_dispatch", span_type="tool_call")
def run_tool(tool_name: str, tool_input: str, session_id: str = "") -> str:
    """Route to the right tool function."""
    if tool_name == "calculator":
        return calculator(tool_input, session_id=session_id)
    if tool_name == "get_datetime":
        return get_datetime(session_id=session_id)
    if tool_name == "web_search":
        return web_search(tool_input, session_id=session_id)
    if tool_name == "summarize":
        return summarize_text(tool_input, session_id=session_id)
    if tool_name == "unit_converter":
        parts = tool_input.split()
        if len(parts) >= 3:
            try:
                val = float(parts[0])
                return unit_converter(val, parts[1], parts[2], session_id=session_id)
            except ValueError:
                pass
        return f"unit_converter needs format: '<value> <from_unit> <to_unit>'"
    if tool_name == "none":
        return ""
    return f"Unknown tool '{tool_name}'"


# ---------------------------------------------------------------------------
# Main agent — this is the root @trace span
# ---------------------------------------------------------------------------

@trace(name="agent_run", span_type="agent")
def run_agent(question: str, session_id: str = "") -> dict:
    """
    Multi-tool agent. Decorated with @trace — becomes the root trace since
    it's the outermost call. session_id kwarg is auto-detected by ObTrac
    and links all turns of the same conversation in the Sessions dashboard.

    Returns:
        {"answer": str, "tool_used": str, "tool_result": str}
    """
    # Step 1: Ask LLM which tool to use
    agent_tpl = _get_prompt_safe("agent_system", _FALLBACK_AGENT_SYSTEM)
    agent_prompt = agent_tpl.replace("{{question}}", question)
    tool_decision_raw = llm_call(agent_prompt, session_id=session_id)

    # Parse JSON from LLM response
    tool_name = "none"
    tool_input = ""
    try:
        # Extract JSON even if LLM wraps it in markdown
        json_match = re.search(r'\{[^{}]+\}', tool_decision_raw, re.DOTALL)
        if json_match:
            decision = json.loads(json_match.group())
            tool_name = decision.get("tool", "none")
            tool_input = decision.get("input", "")
    except (json.JSONDecodeError, AttributeError):
        tool_name = "none"

    # Step 2: Run the tool
    tool_result = run_tool(tool_name, tool_input, session_id=session_id)

    # Step 3: Generate final answer
    answer_tpl = _get_prompt_safe("final_answer", _FALLBACK_FINAL_ANSWER)
    final_prompt = (
        answer_tpl
        .replace("{{question}}", question)
        .replace("{{tool_name}}", tool_name)
        .replace("{{tool_result}}", tool_result or "No tool result")
    )
    answer = llm_call(final_prompt, session_id=session_id)

    return {
        "answer": answer,
        "tool_used": tool_name,
        "tool_result": tool_result,
    }
