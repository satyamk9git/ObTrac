"""
ObTrac SDK - Open Source RAG Observability & Evaluation Framework
"""

from obtrac_sdk.decorators import trace, observe
from obtrac_sdk.context import ObTracContext
from obtrac_sdk.llm_gateway import LLMGateway
from obtrac_sdk.config import ObTracConfig, CostConfig, get_config, configure_llm

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
) -> ObTracConfig:
    """
    Create and set the global ObTrac configuration.

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
    return cfg


__version__ = "0.1.0"

__all__ = [
    "obtrac_config",
    "trace",
    "observe",
    "log_llm_usage",
    "ObTracConfig",
    "configure_llm",
    "get_config",
    "ObTracContext",
    "LLMGateway",
]
