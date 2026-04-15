"""
Trace context management using Python contextvars.
Maintains trace/span hierarchy across nested function calls.
"""

import contextvars
from obtrac_sdk.models import Trace, Span

# Context variables for trace propagation
_current_trace: contextvars.ContextVar[Trace | None] = contextvars.ContextVar(
    "_current_trace", default=None
)
_current_span: contextvars.ContextVar[Span | None] = contextvars.ContextVar(
    "_current_span", default=None
)


class ObTracContext:
    """Manages the current trace and span context."""

    @staticmethod
    def get_current_trace() -> Trace | None:
        return _current_trace.get()

    @staticmethod
    def set_current_trace(trace: Trace) -> contextvars.Token:
        return _current_trace.set(trace)

    @staticmethod
    def reset_trace(token: contextvars.Token):
        try:
            _current_trace.reset(token)
        except ValueError:
            # Token was created in a different Context (e.g. async generator
            # resumed in a different asyncio task). reset() requires the same
            # Context; set(None) is safe across boundaries — best-effort cleanup.
            _current_trace.set(None)

    @staticmethod
    def get_current_span() -> Span | None:
        return _current_span.get()

    @staticmethod
    def set_current_span(span: Span) -> contextvars.Token:
        return _current_span.set(span)

    @staticmethod
    def reset_span(token: contextvars.Token):
        try:
            _current_span.reset(token)
        except ValueError:
            # Same cross-context issue — fall back to set(None)
            _current_span.set(None)

    @staticmethod
    def log_llm_usage(
        tokens: dict = None,
        cost: float = None,
        model: str = None,
    ):
        """
        Attach token/cost/model info to the current span.

        Cost priority:
        1. If `cost` > 0, use it (e.g. from LiteLLM)
        2. Else auto-calculate from global init(cost={...}) config
        3. Else $0
        """
        span = _current_span.get()
        if span:
            if tokens:
                span.tokens = tokens
            if model:
                span.model = model

            if cost and cost > 0:
                span.cost_usd = cost
            else:
                # Priority: span-level cost_config > global cost config
                prompt_tok = (tokens or {}).get("prompt", 0) or 0
                compl_tok = (tokens or {}).get("completion", 0) or 0

                span_cost_config = (span.metadata or {}).get("cost_config")
                if span_cost_config:
                    p_rate = span_cost_config.get("input_token_1k", 0)
                    c_rate = span_cost_config.get("output_token_1k", 0)
                    span.cost_usd = round(
                        (prompt_tok * p_rate / 1000) + (compl_tok * c_rate / 1000), 8
                    )
                else:
                    from obtrac_sdk.config import get_config
                    cfg = get_config()
                    span.cost_usd = cfg.cost.calculate(prompt_tok, compl_tok)
