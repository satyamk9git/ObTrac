"""
The metric registry: name -> MetricDefinition, populated once at import
time. Every call site that used to do `METRIC_INFO.get(m)` or hardcode a
metric name now goes through get_registry() instead.
"""

from __future__ import annotations

import logging

from app.services.metrics.base import MetricDefinition

logger = logging.getLogger("obtrac")


class MetricRegistry:
    def __init__(self):
        self._metrics: dict[str, MetricDefinition] = {}

    def register(self, metric: MetricDefinition) -> None:
        if not metric.key:
            raise ValueError(f"Metric {metric!r} has no key")
        self._metrics[metric.key] = metric

    def get(self, key: str) -> MetricDefinition | None:
        return self._metrics.get(key)

    def all(self) -> dict[str, MetricDefinition]:
        return dict(self._metrics)

    def keys(self) -> list[str]:
        return list(self._metrics.keys())

    def by_category(self) -> dict[str, list[str]]:
        categories: dict[str, list[str]] = {}
        for key, metric in self._metrics.items():
            categories.setdefault(metric.category, []).append(key)
        return categories


_registry: MetricRegistry | None = None


def get_registry() -> MetricRegistry:
    """Process-wide singleton, built on first use."""
    global _registry
    if _registry is None:
        _registry = MetricRegistry()
        register_builtin_metrics(_registry)
        _register_external_adapters(_registry)
    return _registry


def register_builtin_metrics(registry: MetricRegistry) -> None:
    from app.services.metrics.builtin import build_metrics

    for metric in build_metrics():
        registry.register(metric)


def _register_external_adapters(registry: MetricRegistry) -> None:
    """Optional external-framework metrics (DeepEval, MLflow, Phoenix) —
    each adapter module is only importable if its extra is installed
    (`pip install obtrac[deepeval]` etc.), so a missing dependency just
    means fewer metrics show up in /evaluation/metrics-info, not a crash."""
    try:
        from app.services.metrics.deepeval_adapter import build_metrics as build_deepeval_metrics
        for metric in build_deepeval_metrics():
            registry.register(metric)
    except ImportError:
        pass
    except Exception:
        logger.exception("Failed to register DeepEval metrics despite deepeval being importable")

    try:
        from app.services.metrics.mlflow_adapter import build_metrics as build_mlflow_metrics
        for metric in build_mlflow_metrics():
            registry.register(metric)
    except ImportError:
        pass
    except Exception:
        logger.exception("Failed to register MLflow metrics despite mlflow being importable")

    try:
        from app.services.metrics.phoenix_adapter import build_metrics as build_phoenix_metrics
        for metric in build_phoenix_metrics():
            registry.register(metric)
    except ImportError:
        pass
    except Exception:
        logger.exception("Failed to register Phoenix metrics despite arize-phoenix-evals being importable")
