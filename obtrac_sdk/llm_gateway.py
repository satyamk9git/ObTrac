"""
LLM Gateway - Unified interface for all LLM providers via LiteLLM.
Supports: OpenAI, Azure OpenAI, Anthropic (Claude), Google Gemini,
Vertex AI, AWS Bedrock, Ollama, Groq, Together AI, HuggingFace, vLLM.
"""

import logging
from typing import Any

from litellm import completion, embedding
import litellm

from obtrac_sdk.models import LLMConfig, LLMProvider, LLMRole
from obtrac_sdk.config import get_config

logger = logging.getLogger("obtrac")

# Disable LiteLLM's verbose logging
litellm.set_verbose = False

# Provider prefix mapping for LiteLLM model strings
PROVIDER_PREFIX = {
    LLMProvider.OPENAI: "",
    LLMProvider.AZURE_OPENAI: "azure/",
    LLMProvider.ANTHROPIC: "anthropic/",
    LLMProvider.GEMINI: "gemini/",
    LLMProvider.VERTEX_AI: "vertex_ai/",
    LLMProvider.BEDROCK: "bedrock/",
    LLMProvider.OLLAMA: "ollama/",
    LLMProvider.GROQ: "groq/",
    LLMProvider.TOGETHER: "together_ai/",
    LLMProvider.HUGGINGFACE: "huggingface/",
    LLMProvider.VLLM: "openai/",  # vLLM exposes OpenAI-compatible API
    LLMProvider.CUSTOM: "",
}


class LLMGateway:
    """
    Unified LLM access layer wrapping LiteLLM.
    Manages multiple LLM configurations with role-based routing.
    """

    def __init__(self):
        self._configs: dict[str, LLMConfig] = {}
        # Load from global config
        config = get_config()
        self._configs = dict(config.llm_configs)

    def register(self, llm_config: LLMConfig):
        """Register an LLM configuration."""
        self._configs[llm_config.name] = llm_config

    def unregister(self, name: str):
        """Remove an LLM configuration."""
        self._configs.pop(name, None)

    def list_configs(self) -> list[LLMConfig]:
        """List all registered LLM configurations."""
        return list(self._configs.values())

    def get_by_role(self, role: str) -> LLMConfig | None:
        """Get the first active LLM config with the given role."""
        for cfg in self._configs.values():
            if cfg.role.value == role and cfg.is_active:
                return cfg
        return None

    def call(
        self,
        llm_name: str,
        messages: list[dict[str, str]],
        **overrides,
    ) -> dict[str, Any]:
        """
        Call an LLM by its registered name.

        Returns:
            dict with keys: content, tokens, cost, model, provider
        """
        if llm_name not in self._configs:
            raise ValueError(
                f"LLM '{llm_name}' not registered. "
                f"Available: {list(self._configs.keys())}"
            )

        cfg = self._configs[llm_name]
        model_string = self._build_model_string(cfg)
        kwargs = self._build_kwargs(cfg, overrides)

        logger.debug(f"Calling LLM: {model_string} (role: {cfg.role.value})")

        response = completion(
            model=model_string,
            messages=messages,
            **kwargs,
        )

        result = {
            "content": response.choices[0].message.content,
            "tokens": {
                "prompt": response.usage.prompt_tokens if response.usage else 0,
                "completion": response.usage.completion_tokens if response.usage else 0,
            },
            "cost": getattr(response, "_hidden_params", {}).get("response_cost", 0),
            "model": cfg.model_id,
            "provider": cfg.provider.value,
        }

        return result

    def generate(self, messages: list[dict], **kwargs) -> dict:
        """Call the LLM with role=generator."""
        cfg = self.get_by_role("generator")
        if not cfg:
            raise ValueError("No active LLM with role 'generator' registered.")
        return self.call(cfg.name, messages, **kwargs)

    def judge(self, messages: list[dict], **kwargs) -> dict:
        """Call the LLM with role=judge."""
        cfg = self.get_by_role("judge")
        if not cfg:
            raise ValueError("No active LLM with role 'judge' registered.")
        return self.call(cfg.name, messages, **kwargs)

    def embed(self, text: str | list[str], llm_name: str = None) -> list[list[float]]:
        """
        Get embeddings using the embedder LLM or a specific one.
        """
        if llm_name:
            cfg = self._configs[llm_name]
        else:
            cfg = self.get_by_role("embedder")
            if not cfg:
                raise ValueError("No active LLM with role 'embedder' registered.")

        model_string = self._build_model_string(cfg)
        kwargs = {}
        if cfg.api_key:
            kwargs["api_key"] = cfg.api_key
        if cfg.api_base:
            kwargs["api_base"] = cfg.api_base

        if isinstance(text, str):
            text = [text]

        response = embedding(model=model_string, input=text, **kwargs)
        return [item["embedding"] for item in response.data]

    def _build_model_string(self, cfg: LLMConfig) -> str:
        """Build the LiteLLM model string from provider + model_id."""
        prefix = PROVIDER_PREFIX.get(cfg.provider, "")
        if cfg.provider == LLMProvider.AZURE_OPENAI and cfg.azure_deployment:
            # LiteLLM format for Azure: azure/<deployment_name>
            return f"azure/{cfg.azure_deployment}"
        return f"{prefix}{cfg.model_id}"

    def _build_kwargs(self, cfg: LLMConfig, overrides: dict) -> dict:
        """Build provider-specific kwargs for LiteLLM."""
        kwargs = {
            "temperature": overrides.get("temperature", cfg.temperature),
            "top_p": overrides.get("top_p", cfg.top_p),
        }

        # Azure gpt-4o requires max_completion_tokens instead of max_tokens
        if cfg.provider == LLMProvider.AZURE_OPENAI:
            kwargs["max_completion_tokens"] = overrides.get("max_tokens", cfg.max_tokens)
        else:
            kwargs["max_tokens"] = overrides.get("max_tokens", cfg.max_tokens)

        if cfg.api_key:
            kwargs["api_key"] = cfg.api_key

        # Provider-specific
        if cfg.provider == LLMProvider.AZURE_OPENAI:
            # Azure OpenAI: api_base = endpoint URL
            if cfg.api_base:
                kwargs["api_base"] = cfg.api_base
            if cfg.api_version:
                kwargs["api_version"] = cfg.api_version
            # model_id stores the model name (e.g., gpt-4o) for display,
            # but LiteLLM routes via deployment name in the model string

        elif cfg.provider == LLMProvider.VERTEX_AI:
            if cfg.api_base:
                kwargs["api_base"] = cfg.api_base
            if cfg.vertex_project:
                kwargs["vertex_project"] = cfg.vertex_project
            if cfg.vertex_location:
                kwargs["vertex_location"] = cfg.vertex_location

        elif cfg.provider == LLMProvider.BEDROCK:
            if cfg.aws_region:
                kwargs["aws_region_name"] = cfg.aws_region

        else:
            if cfg.api_base:
                kwargs["api_base"] = cfg.api_base

        return kwargs

    def test_connection(self, llm_name: str) -> dict:
        """Test if an LLM connection is working."""
        try:
            result = self.call(
                llm_name,
                messages=[{"role": "user", "content": "Say 'ok'"}],
                max_tokens=5,
            )
            return {"status": "success", "response": result["content"]}
        except Exception as e:
            return {"status": "error", "error": str(e)}
