"""
Global configuration for ObTrac SDK.
"""

from dataclasses import dataclass, field
from obtrac_sdk.models import LLMConfig, LLMProvider, LLMRole


@dataclass
class CostConfig:
    """Token pricing configuration. Set once, inherited by all decorators."""
    input_token_1k: float = 0.0   # Cost per 1K prompt/input tokens (USD)
    output_token_1k: float = 0.0  # Cost per 1K completion/output tokens (USD)

    def calculate(self, prompt_tokens: int, completion_tokens: int) -> float:
        if self.input_token_1k == 0 and self.output_token_1k == 0:
            return 0.0
        cost = (prompt_tokens * self.input_token_1k / 1000) + \
               (completion_tokens * self.output_token_1k / 1000)
        return round(cost, 8)


@dataclass
class ObTracConfig:
    project: str = "default"
    backend_url: str = "http://localhost:8000"
    mlflow_tracking_uri: str = "http://localhost:5000"
    llm_configs: dict[str, LLMConfig] = field(default_factory=dict)
    auto_eval: bool = True
    default_metrics: list[str] = field(
        default_factory=lambda: ["faithfulness", "answer_relevancy"]
    )
    cost: CostConfig = field(default_factory=CostConfig)
    user: str = ""
    session_id: str = ""


_global_config: ObTracConfig | None = None


def _set_global_config(cfg: ObTracConfig):
    """Set the global config (used by obtrac_config factory)."""
    global _global_config
    _global_config = cfg


def init(
    project: str = "default",
    backend_url: str = "http://localhost:8000",
    mlflow_tracking_uri: str = "http://localhost:5000",
    auto_eval: bool = True,
    default_metrics: list[str] = None,
    cost: dict = None,
    user: str = "",
) -> ObTracConfig:
    """
    Initialize ObTrac with project settings.

    Args:
        cost: Token pricing dict, e.g. {"input_token_1k": 0.0025, "output_token_1k": 0.01}
        user: Username for tracking who made requests
    """
    global _global_config

    cost_config = CostConfig()
    if cost:
        cost_config = CostConfig(
            input_token_1k=cost.get("input_token_1k", 0),
            output_token_1k=cost.get("output_token_1k", 0),
        )

    _global_config = ObTracConfig(
        project=project,
        backend_url=backend_url,
        mlflow_tracking_uri=mlflow_tracking_uri,
        auto_eval=auto_eval,
        default_metrics=default_metrics or ["faithfulness", "answer_relevancy"],
        cost=cost_config,
        user=user,
    )
    return _global_config


def get_config() -> ObTracConfig:
    global _global_config
    if _global_config is None:
        _global_config = ObTracConfig()
    return _global_config


def configure_llm(
    name: str,
    provider: str,
    model: str,
    role: str = "generator",
    api_key: str = None,
    api_base: str = None,
    api_version: str = None,
    azure_deployment: str = None,
    vertex_project: str = None,
    vertex_location: str = None,
    vertex_credentials: str = None,
    aws_region: str = None,
    aws_access_key: str = None,
    aws_secret_key: str = None,
    temperature: float = 0.3,
    max_tokens: int = 2048,
) -> LLMConfig:
    """Register an LLM configuration."""
    config = get_config()
    llm_config = LLMConfig(
        name=name,
        provider=LLMProvider(provider),
        model_id=model,
        role=LLMRole(role),
        api_key=api_key,
        api_base=api_base,
        api_version=api_version,
        azure_deployment=azure_deployment,
        vertex_project=vertex_project,
        vertex_location=vertex_location,
        vertex_credentials=vertex_credentials,
        aws_region=aws_region,
        aws_access_key=aws_access_key,
        aws_secret_key=aws_secret_key,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    config.llm_configs[name] = llm_config
    return llm_config
