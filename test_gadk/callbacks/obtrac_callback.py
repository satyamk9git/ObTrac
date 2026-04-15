"""
ObTrac callbacks for Google ADK 1.x agents.

Correct signatures for ADK 1.26+:
  before_agent_callback(context: Context) -> Content | None
  after_agent_callback(context: Context) -> Content | None
  before_tool_callback(tool, args, context: Context) -> dict | None
  after_tool_callback(tool, args, context: Context, response: dict) -> dict | None

context.session.id  — the stable conversation ID ObTrac uses as session_id.
"""

import threading
import time
import logging
from typing import Optional

import requests

from obtrac_sdk.config import get_config
from obtrac_sdk.context import ObTracContext
from obtrac_sdk.models import Trace, SpanStatus

logger = logging.getLogger("obtrac.adk")

# session_id → (Trace, context_token, start_time)
_active_traces: dict = {}


def _session_id(context) -> str:
    try:
        return str(context.session.id)
    except Exception:
        return ""


def _text_from_content(content) -> str:
    """Extract plain text from an ADK Content object or string."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if hasattr(content, "parts"):
        return " ".join(
            p.text for p in content.parts
            if hasattr(p, "text") and p.text
        ).strip()
    return str(content).strip()


def _last_user_message(context) -> str:
    """Extract the most recent user message from the session."""
    try:
        for ev in reversed(list(context.session.events)):
            if getattr(ev, "author", None) == "user":
                text = _text_from_content(getattr(ev, "content", None))
                if text:
                    return text
    except Exception:
        pass
    return ""


def _last_agent_answer(context) -> str:
    """Extract the agent's final response from session events."""
    try:
        for ev in reversed(list(context.session.events)):
            author = getattr(ev, "author", "") or ""
            if author.lower() in ("user",):
                continue
            # Prefer is_final_response events
            try:
                if not ev.is_final_response():
                    continue
            except Exception:
                pass
            text = _text_from_content(getattr(ev, "content", None))
            if text:
                return text
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# Agent callbacks — ADK 1.26 signature: (context) → Content | None
# ---------------------------------------------------------------------------

def obtrac_before_agent(callback_context) -> None:
    """Start an ObTrac root Trace at the beginning of each agent turn."""
    context = callback_context
    try:
        sid = _session_id(context)
        query = _last_user_message(context)  # user's question for this turn
        agent_name = getattr(context, "agent_name", None) or "adk_agent"
        cfg = get_config()

        trace_obj = Trace(
            project=cfg.project,
            name=agent_name,
            user=cfg.user,
            session_id=sid,
            query=query,
        )
        token = ObTracContext.set_current_trace(trace_obj)
        key = sid or str(id(context))
        _active_traces[key] = (trace_obj, token, time.time())
        print(f"[ObTrac] trace started | agent={agent_name} | session={sid[:8]}", flush=True)
    except Exception as e:
        print(f"[ObTrac] before_agent ERROR: {e}", flush=True)
    return None


def obtrac_after_agent(callback_context) -> None:
    """Finalize and ship the ObTrac Trace at the end of each agent turn."""
    context = callback_context
    try:
        sid = _session_id(context)
        key = sid or str(id(context))

        if key not in _active_traces:
            print(f"[ObTrac] after_agent: no active trace for key={key[:8]}", flush=True)
            return None

        trace_obj, token, _ = _active_traces.pop(key)

        answer = _last_agent_answer(context)
        if answer:
            trace_obj.answer = answer[:2000]

        trace_obj.finish()

        # Collect context from retrieval spans
        for span in trace_obj.spans:
            if span.span_type and "retrieval" in str(span.span_type):
                r = (span.outputs or {}).get("result", "")
                if r:
                    trace_obj.context += str(r) + "\n"

        cfg = get_config()

        def _send():
            try:
                resp = requests.post(
                    f"{cfg.backend_url}/api/v1/traces",
                    json=trace_obj.to_dict(),
                    timeout=30,
                )
                if resp.ok:
                    print(f"[ObTrac] trace stored | id={trace_obj.trace_id[:12]}", flush=True)
                else:
                    print(f"[ObTrac] backend error {resp.status_code}: {resp.text[:200]}", flush=True)
            except Exception as e:
                print(f"[ObTrac] send failed: {e}", flush=True)

        threading.Thread(target=_send, daemon=True).start()
        ObTracContext.reset_trace(token)
    except Exception as e:
        print(f"[ObTrac] after_agent ERROR: {e}", flush=True)
    return None


# ---------------------------------------------------------------------------
# Tool callbacks — ADK 1.26 signature: (tool, args, context) / +(response)
# ---------------------------------------------------------------------------

# tool name → (Span, span_token, start_time)  — per session_id
_active_spans: dict = {}


# ---------------------------------------------------------------------------
# Model callbacks — capture every LLM call as a generation span
# ---------------------------------------------------------------------------

# invocation_id → (Span, span_token, start_time)
_active_model_spans: dict = {}


def obtrac_before_model(callback_context, llm_request) -> None:
    """Create a generation Span before each LLM call."""
    try:
        from obtrac_sdk.models import Span, SpanType
        inv_id = getattr(callback_context, "invocation_id", None) or str(id(callback_context))
        current_trace = ObTracContext.get_current_trace()
        parent_span = ObTracContext.get_current_span()

        # Extract model name from request
        model_name = getattr(llm_request, "model", None) or "unknown"

        # Extract prompt text (last user content)
        prompt_text = ""
        try:
            contents = llm_request.contents or []
            for c in reversed(contents):
                text = _text_from_content(c)
                if text:
                    prompt_text = text[:500]
                    break
        except Exception:
            pass

        span = Span(
            name="llm_call",
            span_type=SpanType.GENERATION,
            trace_id=current_trace.trace_id if current_trace else "",
            parent_span_id=parent_span.span_id if parent_span else None,
            model=model_name,
        )
        span.inputs = {"prompt": prompt_text}
        span_token = ObTracContext.set_current_span(span)
        _active_model_spans[inv_id] = (span, span_token, time.time(), current_trace)
        print(f"[ObTrac] model start | {model_name}", flush=True)
    except Exception as e:
        print(f"[ObTrac] before_model ERROR: {e}", flush=True)
    return None


def obtrac_after_model(callback_context, llm_response) -> None:
    """Finish the generation Span with token usage and response text."""
    try:
        inv_id = getattr(callback_context, "invocation_id", None) or str(id(callback_context))
        if inv_id not in _active_model_spans:
            return None

        span, span_token, _, current_trace = _active_model_spans.pop(inv_id)

        # Extract response text
        response_text = _text_from_content(getattr(llm_response, "content", None))

        # Extract token usage
        try:
            usage = getattr(llm_response, "usage_metadata", None)
            if usage:
                prompt_tok = getattr(usage, "prompt_token_count", 0) or 0
                completion_tok = getattr(usage, "candidates_token_count", 0) or 0
                span.tokens = {"prompt": prompt_tok, "completion": completion_tok}
        except Exception:
            pass

        span.finish(outputs={"response": response_text[:500]})
        ObTracContext.reset_span(span_token)

        if current_trace:
            current_trace.spans.append(span)
            # If no answer set yet on root trace, use this response
            if not current_trace.answer and response_text:
                current_trace.answer = response_text[:2000]

        print(f"[ObTrac] model done  | tokens={span.tokens}", flush=True)
    except Exception as e:
        print(f"[ObTrac] after_model ERROR: {e}", flush=True)
    return None


# ---------------------------------------------------------------------------
# Tool callbacks — capture tool calls as tool_call spans
# ---------------------------------------------------------------------------

def obtrac_before_tool(tool, args: dict, tool_context) -> Optional[dict]:
    """Create a child Span for this tool call and push it to context."""
    try:
        from obtrac_sdk.models import Span, SpanType
        sid = _session_id(tool_context)
        tool_name = getattr(tool, "name", str(tool))

        current_trace = ObTracContext.get_current_trace()
        parent_span = ObTracContext.get_current_span()

        span = Span(
            name=tool_name,
            span_type=SpanType.TOOL_CALL,
            trace_id=current_trace.trace_id if current_trace else "",
            parent_span_id=parent_span.span_id if parent_span else None,
        )
        span.inputs = {k: str(v)[:500] for k, v in (args or {}).items()}
        span_token = ObTracContext.set_current_span(span)

        key = f"{sid}:{tool_name}"
        _active_spans[key] = (span, span_token, time.time(), current_trace)
        print(f"[ObTrac] tool start | {tool_name} | session={sid[:8]}", flush=True)
    except Exception as e:
        print(f"[ObTrac] before_tool ERROR: {e}", flush=True)
    return None


def obtrac_after_tool(tool, args: dict, tool_context, tool_response: dict) -> Optional[dict]:
    """Finish the Span and attach it to the parent trace."""
    try:
        sid = _session_id(tool_context)
        tool_name = getattr(tool, "name", str(tool))
        key = f"{sid}:{tool_name}"

        if key not in _active_spans:
            return None

        span, span_token, _, current_trace = _active_spans.pop(key)
        result = str(tool_response)[:1000] if tool_response else ""
        span.finish(outputs={"result": result})
        ObTracContext.reset_span(span_token)

        if current_trace:
            current_trace.spans.append(span)

        print(f"[ObTrac] tool done  | {tool_name}", flush=True)
    except Exception as e:
        print(f"[ObTrac] after_tool ERROR: {e}", flush=True)
    return None
