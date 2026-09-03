"""
ObTrac metric registry — the single place every evaluation metric (built-in
LLM-judge metrics, external-framework adapters, custom metrics) is defined
and looked up, instead of being hardcoded per call site.
"""

from app.services.metrics.base import MetricDefinition, MetricInput, MetricResult
from app.services.metrics.registry import MetricRegistry, get_registry
from app.services.metrics.runner import MetricRunner

__all__ = [
    "MetricDefinition",
    "MetricInput",
    "MetricResult",
    "MetricRegistry",
    "get_registry",
    "MetricRunner",
]
