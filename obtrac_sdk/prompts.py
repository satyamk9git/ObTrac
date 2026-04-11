"""
Prompt registry client — fetch versioned prompts from the ObTrac backend.

Variable syntax: use double curly braces — {{varname}}.
Single curly braces and JSON-like content are passed through as literal text.

Usage:
    from obtrac_sdk import get_prompt

    # Fetch latest active version
    prompt = get_prompt("rag_answer")
    rendered = prompt.render(question="What is RAG?", context="...")

    # Fetch specific version
    prompt = get_prompt("rag_answer", version=2)
"""

import logging
import re
import time
from typing import Optional

import requests

from obtrac_sdk.config import get_config
from obtrac_sdk.context import ObTracContext

logger = logging.getLogger("obtrac")

# Simple in-memory cache: {(project, name, version): (data, fetched_at)}
_cache: dict = {}
_CACHE_TTL = 60  # seconds

# Variable placeholder regex — only matches {{identifier}} where identifier
# is a valid Python-style identifier (letters, digits, underscores).
# This is intentionally strict so JSON like {"key": "value"} is left alone.
_VAR_PATTERN = re.compile(r"\{\{(\w+)\}\}")


def _render_template(template: str, kwargs: dict, prompt_name: str, version: int, declared_variables: list) -> str:
    """
    Substitute {{varname}} placeholders with values from kwargs.

    Single { and } characters are passed through as literal text — no escaping
    needed. JSON examples in templates work without modification.

    Raises KeyError if the template references a variable that wasn't passed.
    """
    missing: list[str] = []

    def replace(match: re.Match) -> str:
        var = match.group(1)
        if var in kwargs:
            return str(kwargs[var])
        missing.append(var)
        return match.group(0)  # leave it as-is for the error message

    rendered = _VAR_PATTERN.sub(replace, template)

    if missing:
        unique_missing = sorted(set(missing))
        raise KeyError(
            f"Missing variable(s) {unique_missing} for prompt '{prompt_name}' v{version}. "
            f"Required: {declared_variables}"
        )

    return rendered


class Prompt:
    """A prompt template fetched from the registry.

    Use {{varname}} syntax for variables. Single { and } are literal characters,
    so you can paste JSON examples into your prompts without any escaping.
    """

    def __init__(self, name: str, version: int, template: str, variables: list,
                 model: Optional[str] = None, temperature: Optional[float] = None,
                 prompt_id: Optional[str] = None):
        self.name = name
        self.version = version
        self.template = template
        self.variables = variables
        self.model = model
        self.temperature = temperature
        self.id = prompt_id

    def render(self, **kwargs) -> str:
        """
        Render the template by substituting {{varname}} placeholders.

        Records the prompt name + version on the current span (if any)
        so that traces are linked to the prompts they used.

        Example:
            prompt = get_prompt("rag_answer")
            text = prompt.render(question="What is RAG?", context="...")

        Template syntax:
            {{question}}              → substituted with kwargs["question"]
            {"key": "value"}          → literal JSON, passed through unchanged
            { anything that's not    → literal, passed through unchanged
              a valid identifier }
        """
        rendered = _render_template(
            self.template, kwargs, self.name, self.version, self.variables
        )

        # Track usage on the current trace
        try:
            current_trace = ObTracContext.get_current_trace()
            if current_trace:
                used = current_trace.metadata.setdefault("prompts_used", [])
                used.append({"name": self.name, "version": self.version})

            current_span = ObTracContext.get_current_span()
            if current_span:
                current_span.metadata.setdefault("prompts_used", []).append({
                    "name": self.name,
                    "version": self.version,
                })
        except Exception:
            pass

        return rendered

    def __str__(self):
        return f"Prompt('{self.name}', v{self.version})"

    def __repr__(self):
        return self.__str__()


def get_prompt(name: str, version: Optional[int] = None, project: Optional[str] = None) -> Prompt:
    """
    Fetch a prompt from the ObTrac registry.

    Prompts are global — they're accessible from any project. The `project`
    argument is accepted for backward compatibility but ignored.

    Args:
        name: Prompt name (globally unique).
        version: Specific version to fetch. If None, returns the active (latest) version.
        project: Deprecated, accepted but ignored.

    Returns:
        A Prompt object with .render(**variables) method.

    Examples:
        # Latest active version
        prompt = get_prompt("rag_answer")
        text = prompt.render(question="...", context="...")

        # Specific version
        prompt = get_prompt("rag_answer", version=2)
    """
    cfg = get_config()
    backend_url = cfg.backend_url

    cache_key = ("global", name, version or "latest")
    now = time.time()

    # Check cache
    if cache_key in _cache:
        data, fetched_at = _cache[cache_key]
        if now - fetched_at < _CACHE_TTL:
            return _build_prompt(name, data)

    # Fetch from backend
    try:
        if version is not None:
            url = f"{backend_url}/api/v1/prompts/{name}/versions/{version}"
        else:
            url = f"{backend_url}/api/v1/prompts/{name}/latest"

        resp = requests.get(url, timeout=10)
        if resp.status_code == 404:
            raise ValueError(f"Prompt '{name}' (version={version or 'latest'}) not found")
        resp.raise_for_status()
        data = resp.json()

        # Cache it
        _cache[cache_key] = (data, now)

        return _build_prompt(name, data)
    except requests.RequestException as e:
        # Try cache as fallback
        if cache_key in _cache:
            logger.warning(f"Backend unreachable, using cached prompt: {e}")
            data, _ = _cache[cache_key]
            return _build_prompt(name, data)
        raise RuntimeError(f"Failed to fetch prompt '{name}': {e}")


def _build_prompt(name: str, data: dict) -> Prompt:
    return Prompt(
        name=name,
        version=data.get("version", 1),
        template=data.get("template", ""),
        variables=data.get("variables", []),
        model=data.get("model"),
        temperature=data.get("temperature"),
        prompt_id=data.get("id"),
    )


def clear_prompt_cache():
    """Clear the local prompt cache. Useful for testing or after publishing new versions."""
    _cache.clear()
