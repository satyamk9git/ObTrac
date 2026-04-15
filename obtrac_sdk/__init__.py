"""
ObTrac SDK - Open Source RAG Observability & Evaluation Framework
"""

from obtrac_sdk.decorators import trace, observe
from obtrac_sdk.context import ObTracContext
from obtrac_sdk.llm_gateway import LLMGateway
from obtrac_sdk.config import ObTracConfig, CostConfig, get_config, configure_llm
from obtrac_sdk.prompts import get_prompt, Prompt, clear_prompt_cache

# Convenience
log_llm_usage = ObTracContext.log_llm_usage

# Factory function
def obtrac_config(
    project: str = "default",
    backend_url: str = "http://localhost:8100",
    user: str = "",
    session_id: str = "",
    auto_eval: bool = False,
    default_metrics: list[str] = None,
    cost: dict = None,
    auto_create_project: bool = True,
) -> ObTracConfig:
    """
    Create and set the global ObTrac configuration.

    By default, the project is auto-created on the backend if it doesn't
    already exist — so it shows up in the dashboard immediately, even
    before the first trace is logged. Set auto_create_project=False to
    skip this (e.g. in offline scripts where backend is unreachable).

    Usage:
        from obtrac_sdk import obtrac_config, trace, observe

        config = obtrac_config(
            project="my-app",
            user="satyam",
            cost={"input_token_cost": 0.0025, "output_token_cost": 0.01},
        )
    """
    from obtrac_sdk.config import _set_global_config

    cost_config = CostConfig()
    if cost:
        cost_config = CostConfig(
            input_token_1k=cost.get("input_token_cost", cost.get("input_token_1k", 0)),
            output_token_1k=cost.get("output_token_cost", cost.get("output_token_1k", 0)),
        )

    cfg = ObTracConfig(
        project=project,
        backend_url=backend_url,
        user=user,
        session_id=session_id,
        auto_eval=auto_eval,
        default_metrics=default_metrics or ["faithfulness", "answer_relevancy"],
        cost=cost_config,
    )
    _set_global_config(cfg)

    # Auto-register the project on the backend so it shows in dropdowns
    # before the first trace is logged. Idempotent and non-blocking on failure.
    if auto_create_project and project:
        try:
            import requests
            requests.post(
                f"{backend_url.rstrip('/')}/api/v1/traces/projects",
                json={"name": project, "description": ""},
                timeout=2,
            )
        except Exception:
            # Backend down / network issue → silent. Project will still
            # be created implicitly when the first trace is logged.
            pass

    return cfg


__version__ = "0.6.6"

__all__ = [
    "obtrac_config",
    "trace",
    "observe",
    "log_llm_usage",
    "get_prompt",
    "Prompt",
    "clear_prompt_cache",
    "ObTracConfig",
    "configure_llm",
    "get_config",
    "ObTracContext",
    "LLMGateway",
]
