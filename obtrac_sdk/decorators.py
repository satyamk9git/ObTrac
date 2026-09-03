"""
Core decorators: @trace (unified) and @observe (deprecated alias) for RAG pipeline instrumentation.

@trace auto-detects:
  - Root vs. child: creates a root Trace when no trace is active, a child Span otherwise.
  - Function type: wraps sync functions, async coroutines, and async generators transparently.

@observe is kept for backward compatibility but emits a DeprecationWarning.
Migrate to @trace — it does everything @observe does and more.
"""

import asyncio
import functools
import inspect
import json
import logging
import threading
import traceback
import warnings
from typing import Callable
from datetime import datetime

import requests

from obtrac_sdk.models import Trace, Span, SpanType, SpanStatus
from obtrac_sdk.context import ObTracContext
from obtrac_sdk.config import get_config

logger = logging.getLogger("obtrac")

# Token counter cache
_tiktoken_encoder = None


def _count_tokens(text: str, model: str = "gpt-4o") -> int:
    """Count tokens using tiktoken. Falls back to word-based estimate."""
    global _tiktoken_encoder
    try:
        if _tiktoken_encoder is None:
            import tiktoken
            try:
                _tiktoken_encoder = tiktoken.encoding_for_model(model)
            except KeyError:
                _tiktoken_encoder = tiktoken.get_encoding("cl100k_base")
        return len(_tiktoken_encoder.encode(str(text)))
    except Exception:
        return len(str(text)) // 4


def _auto_capture_tool_calls(span: Span, result) -> None:
    """If a raw LiteLLM response was returned directly from a @trace'd
    function (the same case _auto_capture_usage handles for tokens),
    also auto-populate span.tool_calls — reuses llm_gateway's own
    extraction so the parsing logic isn't duplicated."""
    if not hasattr(result, "choices"):
        return
    try:
        from obtrac_sdk.llm_gateway import _extract_tool_calls
        tool_calls = _extract_tool_calls(result)
        if tool_calls:
            span.tool_calls = tool_calls
    except Exception:
        pass  # best-effort — never let auto-capture break the actual call


def _auto_capture_usage(span: Span, inputs: dict, result, model_name: str = None):
    """
    Auto-capture token usage from:
    1. LiteLLM response object (has .usage)
    2. tiktoken estimation from inputs/outputs
    """
    if hasattr(result, "usage") and result.usage:
        usage = result.usage
        span.tokens = {
            "prompt": getattr(usage, "prompt_tokens", 0) or 0,
            "completion": getattr(usage, "completion_tokens", 0) or 0,
        }
        span.model = getattr(result, "model", model_name) or model_name
        _auto_capture_tool_calls(span, result)
        litellm_cost = getattr(result, "_hidden_params", {}).get("response_cost", 0)
        if litellm_cost and litellm_cost > 0:
            span.cost_usd = litellm_cost
            return
    elif span.span_type in (SpanType.GENERATION, SpanType.AGENT) and not span.tokens:
        input_text = json.dumps(inputs, default=str) if inputs else ""
        output_text = str(result) if result else ""
        span.tokens = {
            "prompt": _count_tokens(input_text, model_name or "gpt-4o"),
            "completion": _count_tokens(output_text, model_name or "gpt-4o"),
        }

    if span.cost_usd == 0 and span.tokens:
        prompt_tok = span.tokens.get("prompt", 0) or 0
        compl_tok = span.tokens.get("completion", 0) or 0
        span_cost_config = (span.metadata or {}).get("cost_config")
        if span_cost_config:
            p_rate = span_cost_config.get("input_token_1k", 0)
            c_rate = span_cost_config.get("output_token_1k", 0)
            span.cost_usd = round((prompt_tok * p_rate / 1000) + (compl_tok * c_rate / 1000), 8)
        else:
            cfg = get_config()
            span.cost_usd = cfg.cost.calculate(prompt_tok, compl_tok)


def _serialize_safe(obj) -> str:
    """Safely serialize objects for logging."""
    try:
        if isinstance(obj, (str, int, float, bool)):
            return str(obj)
        return json.dumps(obj, default=str, ensure_ascii=False)[:5000]
    except Exception:
        return str(obj)[:5000]


def _capture_inputs(func, args, kwargs) -> dict:
    """Extract named function arguments into a flat dict."""
    try:
        arg_names = func.__code__.co_varnames[: func.__code__.co_argcount]
        captured = {
            arg_names[i]: _serialize_safe(args[i])
            for i in range(min(len(args), len(arg_names)))
        }
        captured.update({k: _serialize_safe(v) for k, v in kwargs.items()})
        return captured
    except Exception:
        return {"raw_args": str(args)[:1000]}


def _send_trace_background(trace_obj: Trace, cfg, eval_metrics: list = None):
    """Fire-and-forget: POST trace to backend in a daemon thread."""
    def _work():
        trace_dict = trace_obj.to_dict()
        if cfg.auto_eval and eval_metrics:
            trace_dict["eval_status"] = "pending"
            trace_dict["eval_metrics"] = eval_metrics
        try:
            resp = requests.post(
                f"{cfg.backend_url}/api/v1/traces",
                json=trace_dict,
                timeout=180,
            )
            if resp.ok:
                result = resp.json()
                logger.info(
                    f"Trace stored: {result.get('trace_id', '')[:12]} "
                    f"eval={result.get('eval_status', 'none')}"
                )
            else:
                logger.warning(
                    f"ObTrac backend rejected trace (HTTP {resp.status_code}) at "
                    f"{cfg.backend_url}/api/v1/traces — body: {resp.text[:300]}"
                )
        except Exception as e:
            logger.warning(
                f"ObTrac backend send failed at {cfg.backend_url}/api/v1/traces: "
                f"{type(e).__name__}: {e}"
            )

    threading.Thread(target=_work, daemon=True).start()


def _collect_context_from_spans(trace_obj: Trace):
    """Back-fill trace.context from retrieval spans when not explicitly set."""
    if trace_obj.context:
        return
    for span in trace_obj.spans:
        if span.span_type == SpanType.RETRIEVAL:
            trace_obj.retrieved_chunks.append(span.outputs)
            if "result" in span.outputs:
                trace_obj.context += str(span.outputs["result"]) + "\n"
        field_map = (span.metadata or {}).get("field_map", {})
        if "context" in field_map and field_map["context"] == "return":
            trace_obj.context += str(span.outputs.get("result", "")) + "\n"


def _resolve_field(field_name, args_dict, result):
    if field_name == "return":
        return _serialize_safe(result)
    return args_dict.get(field_name, "")


_SESSION_KEYS = ("session_id", "thread_id", "conversation_id", "chat_id", "run_id")


def _extract_session_id(args, kwargs) -> str | None:
    """
    Scan all function arguments for a conversation/session ID.

    Framework-agnostic — no dependency on LangGraph, ADK, CrewAI, etc.
    Works with ANY framework or plain Python code that passes a session/thread
    identifier somewhere in the function signature.

    Detection order (first match wins):
    1. kwargs with a well-known name  → session_id, thread_id, conversation_id,
                                        chat_id, run_id
    2. dict argument keys             → same names (e.g. LangGraph RunnableConfig
                                        or any config dict)
    3. nested dict under "configurable" → thread_id  (LangGraph convention)
    4. object attributes              → same names on any object
    5. object.session.id              → nested session objects (ADK convention)
    """
    # 1. Explicit kwargs — highest priority, zero ambiguity
    for key in _SESSION_KEYS:
        v = kwargs.get(key)
        if v and isinstance(v, str):
            return v

    all_values = list(args) + list(kwargs.values())

    for val in all_values:
        if val is None:
            continue

        # 2 & 3. Dict arguments
        if isinstance(val, dict):
            for key in _SESSION_KEYS:
                v = val.get(key)
                if v and isinstance(v, str):
                    return v
            # Nested configurable sub-dict (LangGraph / LangChain convention)
            nested = val.get("configurable")
            if isinstance(nested, dict):
                for key in _SESSION_KEYS:
                    v = nested.get(key)
                    if v and isinstance(v, str):
                        return v

        # 4. Object attributes — works for any dataclass, Pydantic model, custom class
        for attr in _SESSION_KEYS:
            v = getattr(val, attr, None)
            if v and isinstance(v, str):
                return v

        # 5. Nested .session object — .session.id or .session.session_id
        session = getattr(val, "session", None)
        if session is not None:
            for attr in ("id", "session_id"):
                v = getattr(session, attr, None)
                if v and isinstance(v, str):
                    return v

        # 6. Google ADK ToolContext / CallbackContext — .session.id (ADK 1.x)
        #    Already covered by check #5 above (.session.id).
        #    Legacy ADK: .invocation_context.session.id
        inv_ctx = getattr(val, "invocation_context", None)
        if inv_ctx is not None:
            session = getattr(inv_ctx, "session", None)
            if session is not None:
                for attr in ("id", "session_id"):
                    v = getattr(session, attr, None)
                    if v and isinstance(v, str):
                        return v

    return None


def _build_root_trace(cfg, trace_name: str, args=(), kwargs=None) -> Trace:
    # Explicit config session_id wins; fall back to auto-detection from args
    session_id = cfg.session_id or _extract_session_id(args, kwargs or {})
    return Trace(
        project=cfg.project,
        name=trace_name,
        user=cfg.user,
        session_id=session_id or "",
    )


def _apply_field_map(trace_obj: Trace, field_map: dict, all_args: dict, result):
    """Apply @trace field mappings (query/context/response/ground_truth) onto a root trace."""
    if "query" in field_map:
        q_val = _resolve_field(field_map["query"], all_args, result)
        if q_val and not trace_obj.query:
            trace_obj.query = str(q_val)
    if "context" in field_map:
        c_val = _resolve_field(field_map["context"], all_args, result)
        if c_val:
            trace_obj.context += str(c_val) + "\n"
    if "response" in field_map:
        r_val = _resolve_field(field_map["response"], all_args, result)
        if r_val:
            trace_obj.answer = str(r_val)
    if "ground_truth" in field_map:
        gt_val = _resolve_field(field_map["ground_truth"], all_args, result)
        if gt_val:
            trace_obj.ground_truth = str(gt_val)


def _apply_tool_fields(span: Span, tool_name: str, tool_result_field: str, all_args: dict, result):
    """Populate span.tool_name/tool_args/tool_result for a @trace(tool_name=...)
    call — tool_args reuses span.inputs (already captured) rather than
    needing its own separate mapping."""
    if not tool_name:
        return
    span.tool_name = tool_name
    span.tool_args = dict(span.inputs) if span.inputs else None
    if tool_result_field:
        span.tool_result = _resolve_field(tool_result_field, all_args, result)


# ---------------------------------------------------------------------------
# Public decorator
# ---------------------------------------------------------------------------

def trace(
    name: str = None,
    span_type: str = "custom",
    model: str = None,
    cost: dict = None,
    metadata: dict = None,
    config=None,
    query: str = None,
    context: str = None,
    response: str = None,
    ground_truth: str = None,
    metrics: list = None,
    tool_name: str = None,
    tool_result: str = None,
):
    """
    Unified decorator for RAG pipeline instrumentation.

    **Root vs. child — auto-detected at call time:**
    - No active trace in context → creates a root Trace (like the old @observe).
    - Active trace exists → creates a child Span inside it (original @trace behavior).

    **Function types — all three handled transparently:**
    - Regular (sync) functions
    - Async coroutines  (``async def``)
    - Async generators  (``async def`` with ``yield``) — e.g. Google ADK / LangGraph agents

    Args:
        name (str): Span / trace name shown in the dashboard.
        span_type (str): One of "retrieval", "generation", "embedding",
            "tool_call", "agent", "planning", "custom".
        model (str): Model name (e.g., "gpt-4o", "gemini-2.5-flash").
        cost (dict): Per-call token pricing. Keys: "input_token_cost",
            "output_token_cost" (both in $/1K tokens).
        metadata (dict): Extra key-value pairs attached to the span.
        config: ObTracConfig instance (overrides global config).
        query (str): Argument name that contains the user query.
            In root mode, sets trace.query. Default: first positional arg.
        context (str): Argument name (or "return") for retrieved context.
            In root mode, sets trace.context.
        response (str): Argument name (or "return") for the LLM answer.
            In root mode, sets trace.answer. Default: "return".
        ground_truth (str): Argument name that contains the expected answer.
            In root mode, sets trace.ground_truth (used for RAGAS evaluation).
        metrics (list[str]): RAGAS metrics to run when auto_eval=True in config.
            E.g. ["faithfulness", "answer_relevancy", "context_precision"].
            Only applies in root mode. Overrides config.default_metrics.
        tool_name (str): Marks this span as a tool call with this tool's
            name — span.tool_args is auto-populated from the function's
            captured inputs, no separate mapping needed. Typically paired
            with span_type="tool_call". E.g. tool_name="web_search".
        tool_result (str): Argument name (or "return") for the tool's
            result, stored on span.tool_result. Default: "return".
            Only applies when tool_name is also set.

    Examples:
        Full RAG pipeline with eval::

            @trace(name="rag_pipeline", span_type="agent",
                   query="question", context="docs", response="return",
                   ground_truth="expected",
                   metrics=["faithfulness", "answer_relevancy"])
            def pipeline(question, docs, expected=None):
                return generate(question, docs)

        Child span — inside an existing trace::

            @trace(name="retrieve", span_type="retrieval", context="return")
            async def retrieve(query, db, k=5):
                return await db.search(query, k=k)

        Async generator — Google ADK / LangGraph agents::

            @trace(name="agent_step", span_type="agent")
            async def run_agent(ctx) -> AsyncIterator[Event]:
                async for event in inner_agent.run(ctx):
                    yield event
    """
    _cost = None
    if cost:
        _cost = {
            "input_token_1k": cost.get("input_token_cost", cost.get("input_token_1k", 0)),
            "output_token_1k": cost.get("output_token_cost", cost.get("output_token_1k", 0)),
        }

    _tool_result_field = (tool_result or "return") if tool_name else None

    _field_map = {}
    if query:
        _field_map["query"] = query
    if context:
        _field_map["context"] = context
    if response:
        _field_map["response"] = response
    if ground_truth:
        _field_map["ground_truth"] = ground_truth

    def decorator(func: Callable) -> Callable:
        span_name = name or func.__name__

        # ------------------------------------------------------------------
        # Sync wrapper
        # ------------------------------------------------------------------
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            cfg = config or get_config()
            current_trace = ObTracContext.get_current_trace()
            is_root = current_trace is None
            trace_token = None

            if is_root:
                current_trace = _build_root_trace(cfg, span_name, args, kwargs)
                if args:
                    current_trace.query = str(args[0])
                trace_token = ObTracContext.set_current_trace(current_trace)

            parent_span = ObTracContext.get_current_span()
            span = Span(
                name=span_name,
                span_type=SpanType(span_type),
                trace_id=current_trace.trace_id if current_trace else "",
                parent_span_id=parent_span.span_id if parent_span else None,
                model=model,
                metadata={
                    **(metadata or {}),
                    **({"cost_config": _cost} if _cost else {}),
                    **({"field_map": _field_map} if _field_map else {}),
                },
            )
            span.inputs = _capture_inputs(func, args, kwargs)
            span_token = ObTracContext.set_current_span(span)

            try:
                result = func(*args, **kwargs)
                span.finish(outputs={"result": _serialize_safe(result)})
                _auto_capture_usage(span, span.inputs, result, model)

                all_args = dict(span.inputs)
                _apply_tool_fields(span, tool_name, _tool_result_field, all_args, result)
                if _field_map and current_trace:
                    _apply_field_map(current_trace, _field_map, all_args, result)
                elif is_root and current_trace:
                    # Default root-mode: return value is the answer
                    current_trace.answer = _serialize_safe(result)

                return result
            except Exception as e:
                span.finish(error=f"{type(e).__name__}: {str(e)}")
                if is_root and current_trace:
                    current_trace.status = SpanStatus.ERROR
                    current_trace.answer = f"Error: {type(e).__name__}: {str(e)}"
                raise
            finally:
                ObTracContext.reset_span(span_token)
                if is_root and current_trace:
                    current_trace.spans.append(span)
                    current_trace.finish()
                    _collect_context_from_spans(current_trace)
                    _eval_metrics = (metrics or cfg.default_metrics) if cfg.auto_eval else None
                    _send_trace_background(current_trace, cfg, _eval_metrics)
                    ObTracContext.reset_trace(trace_token)
                elif current_trace:
                    current_trace.spans.append(span)

        # ------------------------------------------------------------------
        # Async coroutine wrapper
        # ------------------------------------------------------------------
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            cfg = config or get_config()
            current_trace = ObTracContext.get_current_trace()
            is_root = current_trace is None
            trace_token = None

            if is_root:
                current_trace = _build_root_trace(cfg, span_name, args, kwargs)
                if args:
                    current_trace.query = str(args[0])
                trace_token = ObTracContext.set_current_trace(current_trace)

            parent_span = ObTracContext.get_current_span()
            span = Span(
                name=span_name,
                span_type=SpanType(span_type),
                trace_id=current_trace.trace_id if current_trace else "",
                parent_span_id=parent_span.span_id if parent_span else None,
                model=model,
                metadata={
                    **(metadata or {}),
                    **({"cost_config": _cost} if _cost else {}),
                    **({"field_map": _field_map} if _field_map else {}),
                },
            )
            span.inputs = _capture_inputs(func, args, kwargs)
            span_token = ObTracContext.set_current_span(span)

            try:
                result = await func(*args, **kwargs)
                span.finish(outputs={"result": _serialize_safe(result)})
                _auto_capture_usage(span, span.inputs, result, model)

                all_args = dict(span.inputs)
                _apply_tool_fields(span, tool_name, _tool_result_field, all_args, result)
                if _field_map and current_trace:
                    _apply_field_map(current_trace, _field_map, all_args, result)
                elif is_root and current_trace:
                    current_trace.answer = _serialize_safe(result)

                return result
            except Exception as e:
                span.finish(error=f"{type(e).__name__}: {str(e)}")
                if is_root and current_trace:
                    current_trace.status = SpanStatus.ERROR
                    current_trace.answer = f"Error: {type(e).__name__}: {str(e)}"
                raise
            finally:
                ObTracContext.reset_span(span_token)
                if is_root and current_trace:
                    current_trace.spans.append(span)
                    current_trace.finish()
                    _collect_context_from_spans(current_trace)
                    _eval_metrics = (metrics or cfg.default_metrics) if cfg.auto_eval else None
                    _send_trace_background(current_trace, cfg, _eval_metrics)
                    ObTracContext.reset_trace(trace_token)
                elif current_trace:
                    current_trace.spans.append(span)

        # ------------------------------------------------------------------
        # Async generator wrapper
        # ------------------------------------------------------------------
        @functools.wraps(func)
        async def asyncgen_wrapper(*args, **kwargs):
            cfg = config or get_config()
            current_trace = ObTracContext.get_current_trace()
            is_root = current_trace is None
            trace_token = None

            if is_root:
                current_trace = _build_root_trace(cfg, span_name, args, kwargs)
                if args:
                    current_trace.query = str(args[0])
                trace_token = ObTracContext.set_current_trace(current_trace)

            parent_span = ObTracContext.get_current_span()
            span = Span(
                name=span_name,
                span_type=SpanType(span_type),
                trace_id=current_trace.trace_id if current_trace else "",
                parent_span_id=parent_span.span_id if parent_span else None,
                model=model,
                metadata={
                    **(metadata or {}),
                    **({"cost_config": _cost} if _cost else {}),
                    **({"field_map": _field_map} if _field_map else {}),
                },
            )
            span.inputs = _capture_inputs(func, args, kwargs)
            span_token = ObTracContext.set_current_span(span)

            # Accumulate yielded items so we can set answer on the root trace
            yielded_items = []
            error_occurred = None
            try:
                async for item in func(*args, **kwargs):
                    yielded_items.append(item)
                    yield item

                # Generator exhausted normally
                span.finish(outputs={"items_yielded": len(yielded_items)})
                if is_root and current_trace:
                    # Summarise the stream as the answer (first 2000 chars)
                    summary = _serialize_safe(yielded_items)[:2000]
                    current_trace.answer = summary

            except GeneratorExit:
                # Caller stopped iterating early — treat as normal completion
                span.finish(outputs={"items_yielded": len(yielded_items), "note": "early_exit"})
                raise
            except Exception as e:
                error_occurred = e
                span.finish(error=f"{type(e).__name__}: {str(e)}")
                if is_root and current_trace:
                    current_trace.status = SpanStatus.ERROR
                    current_trace.answer = f"Error: {type(e).__name__}: {str(e)}"
                raise
            finally:
                ObTracContext.reset_span(span_token)
                if is_root and current_trace:
                    current_trace.spans.append(span)
                    current_trace.finish()
                    _collect_context_from_spans(current_trace)
                    _eval_metrics = (metrics or cfg.default_metrics) if cfg.auto_eval else None
                    _send_trace_background(current_trace, cfg, _eval_metrics)
                    ObTracContext.reset_trace(trace_token)
                elif current_trace:
                    current_trace.spans.append(span)

        # Route to the right wrapper based on function type
        if inspect.isasyncgenfunction(func):
            return asyncgen_wrapper
        elif asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# ---------------------------------------------------------------------------
# @observe — backward-compatible alias, emits DeprecationWarning
# ---------------------------------------------------------------------------

def observe(
    name: str = None,
    metrics: list = None,
    ground_truth_key: str = None,
    query: str = None,
    context: str = None,
    answer: str = None,
    ground_truth: str = None,
):
    """
    Deprecated. Use @trace instead — it now auto-creates a root trace when
    no trace is active, handles async generators, and supports all the same
    field mappings.

    @observe will be removed in v0.8.0.
    """
    warnings.warn(
        "@observe is deprecated and will be removed in v0.8.0. "
        "Use @trace instead — it auto-detects root vs. child and handles "
        "sync, async, and async generator functions.",
        DeprecationWarning,
        stacklevel=2,
    )

    _query_field = query
    _context_field = context
    _answer_field = answer
    _gt_field = ground_truth or ground_truth_key

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            cfg = get_config()
            trace_name = name or func.__name__
            eval_metrics = metrics or cfg.default_metrics

            current_trace = Trace(
                project=cfg.project,
                name=trace_name,
                user=cfg.user,
                session_id=cfg.session_id,
            )

            try:
                arg_names = func.__code__.co_varnames[: func.__code__.co_argcount]
                all_args = {arg_names[i]: args[i] for i in range(min(len(args), len(arg_names)))}
                all_args.update(kwargs)
            except Exception:
                all_args = dict(kwargs)

            if _query_field and _query_field in all_args:
                current_trace.query = str(all_args[_query_field])
            else:
                q = kwargs.get("query", args[0] if args else "")
                current_trace.query = str(q)

            if _context_field and _context_field in all_args:
                current_trace.context = str(all_args[_context_field])

            if _gt_field and _gt_field in all_args:
                gt = all_args[_gt_field]
                if gt:
                    current_trace.ground_truth = str(gt)

            trace_token = ObTracContext.set_current_trace(current_trace)

            try:
                result = func(*args, **kwargs)

                if _answer_field and _answer_field != "return" and _answer_field in all_args:
                    current_trace.answer = str(all_args[_answer_field])
                else:
                    current_trace.answer = str(result) if result else ""

                current_trace.finish()
                _collect_context_from_spans(current_trace)
                _send_trace_background(current_trace, cfg, eval_metrics if cfg.auto_eval else None)
                return result

            except Exception as e:
                current_trace.finish()
                current_trace.status = SpanStatus.ERROR
                current_trace.answer = f"Error: {type(e).__name__}: {str(e)}"
                logger.error(f"Pipeline error: {e}")
                _send_trace_background(current_trace, cfg)
                raise
            finally:
                ObTracContext.reset_trace(trace_token)

        return wrapper

    return decorator


def _send_to_backend(backend_url: str, trace_obj: Trace):
    """Send trace data to ObTrac backend asynchronously. (Legacy helper)"""
    def _send():
        try:
            resp = requests.post(
                f"{backend_url}/api/v1/traces",
                json=trace_obj.to_dict(),
                timeout=10,
            )
            if not resp.ok:
                logger.warning(
                    f"ObTrac backend rejected trace (HTTP {resp.status_code}) at "
                    f"{backend_url}/api/v1/traces — body: {resp.text[:300]}"
                )
        except Exception as e:
            logger.warning(
                f"ObTrac backend send failed at {backend_url}/api/v1/traces: "
                f"{type(e).__name__}: {e}"
            )

    threading.Thread(target=_send, daemon=True).start()
