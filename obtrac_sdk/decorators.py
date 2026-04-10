"""
Core decorators: @trace and @observe for RAG pipeline instrumentation.
"""

import functools
import traceback
import json
import logging
from typing import Callable
from datetime import datetime

from obtrac_sdk.models import Trace, Span, SpanType, SpanStatus
from obtrac_sdk.context import ObTracContext
from obtrac_sdk.config import get_config

# Lazy imports — MLflow and RAGAS are heavy and may not be installed
# They are imported inside the background thread only when needed

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
        # Fallback: rough estimate (1 token ≈ 4 chars)
        return len(str(text)) // 4


def _auto_capture_usage(span: Span, inputs: dict, result, model_name: str = None):
    """
    Auto-capture token usage from:
    1. LiteLLM response object (has .usage)
    2. tiktoken estimation from inputs/outputs
    """
    # Check if result is a LiteLLM/OpenAI response object
    if hasattr(result, "usage") and result.usage:
        usage = result.usage
        span.tokens = {
            "prompt": getattr(usage, "prompt_tokens", 0) or 0,
            "completion": getattr(usage, "completion_tokens", 0) or 0,
        }
        span.model = getattr(result, "model", model_name) or model_name
        # Try to get cost from LiteLLM
        litellm_cost = getattr(result, "_hidden_params", {}).get("response_cost", 0)
        if litellm_cost and litellm_cost > 0:
            span.cost_usd = litellm_cost
            return
    elif span.span_type in (SpanType.GENERATION, SpanType.AGENT) and not span.tokens:
        # Estimate with tiktoken
        input_text = json.dumps(inputs, default=str) if inputs else ""
        output_text = str(result) if result else ""
        span.tokens = {
            "prompt": _count_tokens(input_text, model_name or "gpt-4o"),
            "completion": _count_tokens(output_text, model_name or "gpt-4o"),
        }

    # Auto-calculate cost from span or global config
    if span.cost_usd == 0 and span.tokens:
        prompt_tok = span.tokens.get("prompt", 0) or 0
        compl_tok = span.tokens.get("completion", 0) or 0

        # Priority: span cost_config > global
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
):
    """
    Decorator to trace a function call as a span.

    Captures inputs, outputs, tokens, cost, and latency automatically.
    Use field mapping kwargs to tell ObTrac which arguments are the
    query, context, and response for RAGAS evaluation.

    Args:
        name (str): Span name displayed in the trace tree.
        span_type (str): One of "retrieval", "generation", "embedding",
            "tool_call", "agent", "planning", "custom".
        model (str): Model name (e.g., "gpt-4o", "gemini-2.5-flash").
            Shown in span details and used for model comparison.
        cost (dict): Per-span token pricing. Overrides global config.
            Keys: "input_token_cost" ($/1K input tokens),
                  "output_token_cost" ($/1K output tokens).
        metadata (dict): Any extra key-value metadata to attach to the span.
        config: ObTracConfig instance (overrides global config for this span).
        query (str): Name of the function argument that contains the user query.
            If not set, the first positional argument is used.
        context (str): Name of the function argument that contains the retrieved context.
            Use "return" if the function returns the context (e.g., retrieval functions).
        response (str): Name of the function argument that contains the LLM response.
            Default is "return" (the function's return value).

    Examples:
        Basic — auto-detect inputs/outputs::

            @trace(name="search", span_type="retrieval")
            def search(query, top_k=5):
                return chunks

        With explicit field mapping::

            @trace(name="generate", span_type="generation",
                   model="gpt-4o",
                   query="user_question",
                   context="ctx",
                   response="return",
                   cost={"input_token_cost": 0.0025, "output_token_cost": 0.01})
            def generate(user_question, ctx, temperature=0.3):
                return llm.call(user_question, ctx)

        Retrieval — return value is the context::

            @trace(name="retrieve", span_type="retrieval",
                   query="q", context="return")
            def retrieve(q, db, k=5):
                return db.search(q, k=k)

        Tool call — no field mapping needed::

            @trace(name="calculator", span_type="tool_call")
            def calculate(expression):
                return eval(expression)
    """

    # Normalize cost keys
    _cost = None
    if cost:
        _cost = {
            "input_token_1k": cost.get("input_token_cost", cost.get("input_token_1k", 0)),
            "output_token_1k": cost.get("output_token_cost", cost.get("output_token_1k", 0)),
        }

    # Field mapping
    _field_map = {}
    if query:
        _field_map["query"] = query
    if context:
        _field_map["context"] = context
    if response:
        _field_map["response"] = response

    def _resolve_field(field_name, args_dict, result):
        """Resolve a field mapping to its actual value."""
        if field_name == "return":
            return _serialize_safe(result)
        return args_dict.get(field_name, "")

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            span_name = name or func.__name__
            current_trace = ObTracContext.get_current_trace()
            parent_span = ObTracContext.get_current_span()

            # Create span
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

            # Capture inputs
            try:
                arg_names = func.__code__.co_varnames[: func.__code__.co_argcount]
                span.inputs = {
                    arg_names[i]: _serialize_safe(args[i])
                    for i in range(min(len(args), len(arg_names)))
                }
                span.inputs.update(
                    {k: _serialize_safe(v) for k, v in kwargs.items()}
                )
            except Exception:
                span.inputs = {"raw_args": str(args)[:1000]}

            # Set as current span
            span_token = ObTracContext.set_current_span(span)

            try:
                result = func(*args, **kwargs)
                span.finish(outputs={"result": _serialize_safe(result)})
                # Auto-capture tokens and cost
                _auto_capture_usage(span, span.inputs, result, model)

                # Resolve field mappings → attach to parent trace
                if _field_map and current_trace:
                    all_args = dict(span.inputs)
                    if "query" in _field_map:
                        q_val = _resolve_field(_field_map["query"], all_args, result)
                        if q_val and not current_trace.query:
                            current_trace.query = str(q_val)
                    if "context" in _field_map:
                        c_val = _resolve_field(_field_map["context"], all_args, result)
                        if c_val:
                            current_trace.context += str(c_val) + "\n"
                    if "response" in _field_map:
                        r_val = _resolve_field(_field_map["response"], all_args, result)
                        if r_val:
                            current_trace.answer = str(r_val)

                return result
            except Exception as e:
                span.finish(error=f"{type(e).__name__}: {str(e)}")
                raise
            finally:
                ObTracContext.reset_span(span_token)
                if current_trace:
                    current_trace.spans.append(span)

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            span_name = name or func.__name__
            current_trace = ObTracContext.get_current_trace()
            parent_span = ObTracContext.get_current_span()

            span = Span(
                name=span_name,
                span_type=SpanType(span_type),
                trace_id=current_trace.trace_id if current_trace else "",
                parent_span_id=parent_span.span_id if parent_span else None,
                model=model,
                metadata={**(metadata or {}), **({"cost_config": _cost} if _cost else {})},
            )

            try:
                arg_names = func.__code__.co_varnames[: func.__code__.co_argcount]
                span.inputs = {
                    arg_names[i]: _serialize_safe(args[i])
                    for i in range(min(len(args), len(arg_names)))
                }
                span.inputs.update(
                    {k: _serialize_safe(v) for k, v in kwargs.items()}
                )
            except Exception:
                span.inputs = {"raw_args": str(args)[:1000]}

            span_token = ObTracContext.set_current_span(span)

            try:
                result = await func(*args, **kwargs)
                span.finish(outputs={"result": _serialize_safe(result)})
                _auto_capture_usage(span, span.inputs, result, model)
                return result
            except Exception as e:
                span.finish(error=f"{type(e).__name__}: {str(e)}")
                raise
            finally:
                ObTracContext.reset_span(span_token)
                if current_trace:
                    current_trace.spans.append(span)

        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    return decorator


def observe(
    name: str = None,
    metrics: list[str] = None,
    ground_truth_key: str = None,
    query: str = None,
    context: str = None,
    answer: str = None,
    ground_truth: str = None,
):
    """
    Decorator to observe a full RAG pipeline.

    Creates a root trace, captures RAG data (query, context, answer),
    and triggers RAGAS evaluation if auto_eval is enabled in config.
    Use field mapping kwargs to specify which function arguments
    contain the query, context, answer, and ground truth.

    Args:
        name (str): Pipeline name displayed in dashboard.
        metrics (list[str]): RAGAS metrics to auto-evaluate.
            E.g., ["faithfulness", "answer_relevancy"].
            Only runs if auto_eval=True in obtrac_config.
        ground_truth_key (str): Deprecated. Use ``ground_truth`` instead.
        query (str): Name of the function argument that contains the user query.
            Default: first positional argument.
        context (str): Name of the function argument that contains the context.
            Default: auto-collected from @trace(span_type="retrieval") spans.
        answer (str): Name of the function argument or "return" for the answer.
            Default: "return" (the function's return value).
        ground_truth (str): Name of the function argument with ground truth.

    Examples:
        Basic — auto-detect (first arg = query, return = answer)::

            @observe(name="rag_pipeline",
                     metrics=["faithfulness", "answer_relevancy"])
            def pipeline(question, vectorstore):
                chunks = retrieve(question)
                return generate(question, chunks)

        Explicit field mapping::

            @observe(name="pipeline",
                     query="q",
                     context="docs",
                     answer="return",
                     ground_truth="expected",
                     metrics=["faithfulness", "answer_correctness"])
            def pipeline(q, db, docs=None, expected=None):
                docs = retrieve(q)
                return generate(q, docs)

        Without auto-eval (manual evaluation only)::

            @observe(name="pipeline")
            def pipeline(query):
                return generate(query)
    """
    # Field mappings
    _query_field = query
    _context_field = context
    _answer_field = answer
    _gt_field = ground_truth or ground_truth_key

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            config = get_config()
            trace_name = name or func.__name__
            eval_metrics = metrics or config.default_metrics

            # Create root trace
            current_trace = Trace(
                project=config.project,
                name=trace_name,
                user=config.user,
                session_id=config.session_id,
            )

            # Build args dict for field resolution
            try:
                arg_names = func.__code__.co_varnames[: func.__code__.co_argcount]
                all_args = {arg_names[i]: args[i] for i in range(min(len(args), len(arg_names)))}
                all_args.update(kwargs)
            except Exception:
                all_args = dict(kwargs)

            # Extract query
            if _query_field and _query_field in all_args:
                current_trace.query = str(all_args[_query_field])
            else:
                q = kwargs.get("query", args[0] if args else "")
                current_trace.query = str(q)

            # Extract context if explicitly mapped
            if _context_field and _context_field in all_args:
                current_trace.context = str(all_args[_context_field])

            # Extract ground truth
            if _gt_field and _gt_field in all_args:
                gt = all_args[_gt_field]
                if gt:
                    current_trace.ground_truth = str(gt)

            # Set trace context
            trace_token = ObTracContext.set_current_trace(current_trace)

            try:
                result = func(*args, **kwargs)

                # Extract answer
                if _answer_field and _answer_field != "return" and _answer_field in all_args:
                    current_trace.answer = str(all_args[_answer_field])
                else:
                    current_trace.answer = str(result) if result else ""

                current_trace.finish()

                # Extract context from retrieval spans (if not explicitly mapped)
                if not current_trace.context:
                    for span in current_trace.spans:
                        if span.span_type == SpanType.RETRIEVAL:
                            current_trace.retrieved_chunks.append(span.outputs)
                            if "result" in span.outputs:
                                current_trace.context += str(span.outputs["result"]) + "\n"
                        # Also check spans with context field mapping
                        field_map = (span.metadata or {}).get("field_map", {})
                        if "context" in field_map and field_map["context"] == "return":
                            current_trace.context += str(span.outputs.get("result", "")) + "\n"

                # All post-processing in background thread (non-blocking)
                import threading

                def _post_process(trace_data, cfg, eval_metrics_list):
                    import requests

                    trace_dict = trace_data.to_dict()

                    # If auto_eval, include metrics in the trace POST
                    # Backend will run evaluation synchronously
                    if cfg.auto_eval and eval_metrics_list:
                        trace_dict["eval_status"] = "pending"
                        trace_dict["eval_metrics"] = eval_metrics_list

                    try:
                        resp = requests.post(
                            f"{cfg.backend_url}/api/v1/traces",
                            json=trace_dict,
                            timeout=180,  # Allow time for eval
                        )
                        if resp.ok:
                            result = resp.json()
                            logger.info(f"Trace stored: {result.get('trace_id', '')[:12]} eval={result.get('eval_status', 'none')}")
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

                thread = threading.Thread(
                    target=_post_process,
                    args=(current_trace, config, eval_metrics),
                    daemon=True,
                )
                thread.start()

                return result

            except Exception as e:
                current_trace.finish()
                current_trace.status = SpanStatus.ERROR
                current_trace.answer = f"Error: {type(e).__name__}: {str(e)}"
                logger.error(f"Pipeline error: {e}")

                # Send failed trace to backend too
                import threading
                import requests

                def _send_error_trace(trace_data, cfg):
                    try:
                        requests.post(
                            f"{cfg.backend_url}/api/v1/traces",
                            json=trace_data.to_dict(),
                            timeout=10,
                        )
                    except Exception:
                        pass

                thread = threading.Thread(
                    target=_send_error_trace,
                    args=(current_trace, config),
                    daemon=True,
                )
                thread.start()
                raise
            finally:
                ObTracContext.reset_trace(trace_token)

        return wrapper

    return decorator


def _send_to_backend(backend_url: str, trace_obj: Trace):
    """Send trace data to ObTrac backend asynchronously."""
    import threading
    import requests

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

    thread = threading.Thread(target=_send, daemon=True)
    thread.start()
