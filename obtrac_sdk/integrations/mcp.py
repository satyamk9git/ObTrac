"""
Optional MCP (Model Context Protocol) integration.

wrap_mcp_session() intercepts ClientSession.call_tool — verified directly
against the installed `mcp` package (2.1.1): `call_tool(name, arguments,
...) -> CallToolResult`, where CallToolResult has `content`,
`structured_content`, `is_error`. Each call becomes a tool_call-type Span,
reusing the same tool_name/tool_args/tool_result fields the generic
@trace(tool_name=...) pattern populates (see decorators.py), tagged with
the MCP server name so multiple servers are distinguishable in a trace.

Only importable if `mcp` is installed — callers that don't use MCP never
pay for this.
"""

from __future__ import annotations

import functools
import json
from typing import Any

from obtrac_sdk.context import ObTracContext
from obtrac_sdk.models import Span, SpanType


def _serialize_safe(obj: Any) -> str:
    try:
        if isinstance(obj, (str, int, float, bool)) or obj is None:
            return str(obj)
        return json.dumps(obj, default=str, ensure_ascii=False)[:5000]
    except Exception:
        return str(obj)[:5000]


def wrap_mcp_session(session, server_name: str = "mcp"):
    """Wrap an `mcp.ClientSession` so every `call_tool(...)` is captured as
    a child tool_call span on ObTrac's current trace.

    Transparent wrapper — returns the same session object with `call_tool`
    replaced, so existing MCP client code needs one extra line:

        session = wrap_mcp_session(session, server_name="filesystem")

    A call made with no enclosing @trace(...) function (no current trace)
    is not captured — same as any other tool call, there's nothing to
    attach a span to.
    """
    original_call_tool = session.call_tool

    @functools.wraps(original_call_tool)
    async def call_tool(name: str, arguments: dict | None = None, *args, **kwargs):
        current_trace = ObTracContext.get_current_trace()
        if current_trace is None:
            return await original_call_tool(name, arguments, *args, **kwargs)

        parent_span = ObTracContext.get_current_span()
        span = Span(
            name=f"mcp:{server_name}:{name}",
            span_type=SpanType.TOOL_CALL,
            trace_id=current_trace.trace_id,
            parent_span_id=parent_span.span_id if parent_span else None,
            tool_name=name,
            tool_args=arguments or {},
            metadata={"mcp_server": server_name},
        )
        span.inputs = {"name": name, "arguments": _serialize_safe(arguments)}

        try:
            result = await original_call_tool(name, arguments, *args, **kwargs)
            content = getattr(result, "structured_content", None)
            if content is None:
                content = getattr(result, "content", None)
            is_error = bool(getattr(result, "is_error", False))
            span.tool_result = _serialize_safe(content)
            span.finish(
                outputs={"result": span.tool_result},
                error="MCP tool call reported is_error=True" if is_error else None,
            )
            return result
        except Exception as e:
            span.tool_result = None
            span.finish(error=f"{type(e).__name__}: {str(e)}")
            raise
        finally:
            current_trace.spans.append(span)

    session.call_tool = call_tool
    return session
