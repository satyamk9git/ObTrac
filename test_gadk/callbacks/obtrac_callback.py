"""
ObTrac callbacks for Google ADK agents.

Hooks into ADK's lifecycle to create root-level ObTrac traces around each
agent invocation. Tool-level spans are created by @trace on the tool functions.

Usage — pass to Agent():
    from test_gadk.callbacks import (
        obtrac_before_agent, obtrac_after_agent,
        obtrac_before_tool, obtrac_after_tool,
    )

    root_agent = Agent(
        ...
        before_agent_callback=obtrac_before_agent,
        after_agent_callback=obtrac_after_agent,
        before_tool_callback=obtrac_before_tool,
        after_tool_callback=obtrac_after_tool,
    )
"""

import logging
import time
from typing import Optional

from obtrac_sdk.config import get_config
from obtrac_sdk.context import ObTracContext
from obtrac_sdk.models import Trace, SpanStatus

logger = logging.getLogger("obtrac.adk")

# session_id → (Trace object, context token, start_time)
_active_traces: dict = {}


def _get_session_id(ctx) -> str:
    """Safely extract session ID from ADK InvocationContext or CallbackContext."""
    try:
        # CallbackContext wraps InvocationContext
        inv = getattr(ctx, "invocation_context", ctx)
        return str(inv.session.id)
    except Exception:
        return ""


def _get_query(ctx) -> str:
    """Try to extract the user's latest message text."""
    try:
        inv = getattr(ctx, "invocation_context", ctx)
        events = list(inv.session.events)
        if events:
            last = events[-1]
            parts = getattr(last, "content", None)
            if parts:
                if hasattr(parts, "parts"):
                    return " ".join(p.text for p in parts.parts if hasattr(p, "text"))
                return str(parts)
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# Agent callbacks
# ---------------------------------------------------------------------------

def obtrac_before_agent(callback_context) -> Optional[object]:
    """
    Called by ADK before the agent starts processing a turn.
    Creates a root ObTrac Trace and pushes it to the context.
    """
    try:
        session_id = _get_session_id(callback_context)
        query = _get_query(callback_context)
        agent_name = getattr(callback_context, "agent_name", "adk_agent")
        cfg = get_config()

        trace_obj = Trace(
            project=cfg.project,
            name=agent_name,
            user=cfg.user,
            session_id=session_id,
            query=query,
        )
        token = ObTracContext.set_current_trace(trace_obj)
        _active_traces[session_id or id(callback_context)] = (
            trace_obj, token, time.time()
        )
        logger.debug(f"ObTrac: started trace for agent={agent_name} session={session_id[:8] if session_id else 'n/a'}")
    except Exception as e:
        logger.debug(f"ObTrac before_agent_callback error (non-fatal): {e}")
    return None  # None = don't override the agent's response


def obtrac_after_agent(callback_context, response) -> Optional[object]:
    """
    Called by ADK after the agent finishes a turn.
    Finalizes the ObTrac Trace and ships it to the backend.
    """
    try:
        session_id = _get_session_id(callback_context)
        key = session_id or id(callback_context)

        if key not in _active_traces:
            return None

        trace_obj, token, start_time = _active_traces.pop(key)

        # Extract answer text from ADK response Content
        answer = ""
        try:
            if response and hasattr(response, "parts"):
                answer = " ".join(p.text for p in response.parts if hasattr(p, "text"))
            elif response:
                answer = str(response)
        except Exception:
            pass

        trace_obj.answer = answer[:2000]
        trace_obj.finish()

        # Collect context from retrieval spans
        for span in trace_obj.spans:
            if span.span_type and "retrieval" in str(span.span_type):
                result = (span.outputs or {}).get("result", "")
                if result:
                    trace_obj.context += str(result) + "\n"

        cfg = get_config()

        import threading, requests
        def _send():
            try:
                resp = requests.post(
                    f"{cfg.backend_url}/api/v1/traces",
                    json=trace_obj.to_dict(),
                    timeout=30,
                )
                if resp.ok:
                    logger.info(f"ObTrac: trace stored {trace_obj.trace_id[:12]}")
                else:
                    logger.warning(f"ObTrac: backend {resp.status_code} — {resp.text[:200]}")
            except Exception as e:
                logger.warning(f"ObTrac: send failed — {e}")

        threading.Thread(target=_send, daemon=True).start()
        ObTracContext.reset_trace(token)
        logger.debug(f"ObTrac: finished trace for session={session_id[:8] if session_id else 'n/a'}")
    except Exception as e:
        logger.debug(f"ObTrac after_agent_callback error (non-fatal): {e}")
    return None


# ---------------------------------------------------------------------------
# Tool callbacks (lightweight — main span created by @trace on tool functions)
# ---------------------------------------------------------------------------

def obtrac_before_tool(tool, args: dict, tool_context) -> Optional[dict]:
    """
    Called by ADK before each tool invocation.
    Logs the tool call — the actual span is created by @trace on the tool function.
    """
    try:
        session_id = _get_session_id(tool_context)
        tool_name = getattr(tool, "name", str(tool))
        logger.debug(f"ObTrac: tool start name={tool_name} session={session_id[:8] if session_id else 'n/a'}")
    except Exception:
        pass
    return None  # None = proceed normally


def obtrac_after_tool(tool, args: dict, tool_context, tool_response: dict) -> Optional[dict]:
    """
    Called by ADK after each tool invocation.
    """
    try:
        tool_name = getattr(tool, "name", str(tool))
        logger.debug(f"ObTrac: tool done name={tool_name}")
    except Exception:
        pass
    return None  # None = return original response unchanged
