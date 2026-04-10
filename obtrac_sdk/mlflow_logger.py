"""
MLflow integration for logging traces, metrics, and artifacts.
"""

import json
import logging
from typing import Any

import mlflow
from mlflow.tracking import MlflowClient

from obtrac_sdk.models import Trace

logger = logging.getLogger("obtrac")


class MLflowLogger:
    """Logs ObTrac traces and metrics to MLflow."""

    def __init__(self, tracking_uri: str = "http://localhost:5000"):
        self.tracking_uri = tracking_uri
        mlflow.set_tracking_uri(tracking_uri)
        self._client = MlflowClient(tracking_uri)

    def _get_or_create_experiment(self, project: str) -> str:
        """Get or create an MLflow experiment for the project."""
        experiment = mlflow.get_experiment_by_name(project)
        if experiment:
            return experiment.experiment_id
        return mlflow.create_experiment(project)

    def log_trace(self, trace: Trace):
        """Log a complete trace as an MLflow run."""
        experiment_id = self._get_or_create_experiment(trace.project)

        with mlflow.start_run(
            experiment_id=experiment_id,
            run_name=f"trace_{trace.trace_id[:8]}",
        ) as run:
            # Log parameters
            mlflow.log_param("trace_id", trace.trace_id)
            mlflow.log_param("pipeline_name", trace.name)
            mlflow.log_param("status", trace.status.value)
            mlflow.log_param("query", trace.query[:250] if trace.query else "")

            # Log span-level model info
            for span in trace.spans:
                if span.model:
                    mlflow.log_param(f"model_{span.name}", span.model)

            # Log performance metrics
            mlflow.log_metric("total_latency_ms", trace.total_latency_ms)
            mlflow.log_metric("total_cost_usd", trace.total_cost_usd)
            mlflow.log_metric(
                "total_prompt_tokens",
                trace.total_tokens.get("prompt", 0),
            )
            mlflow.log_metric(
                "total_completion_tokens",
                trace.total_tokens.get("completion", 0),
            )
            mlflow.log_metric("num_spans", len(trace.spans))

            # Log per-span latency
            for span in trace.spans:
                mlflow.log_metric(f"latency_{span.name}_ms", span.latency_ms)

            # Log RAGAS metrics if available
            for metric_name, metric_value in trace.metrics.items():
                mlflow.log_metric(metric_name, metric_value)

            # Log trace data as artifact
            trace_artifact = {
                "trace_id": trace.trace_id,
                "query": trace.query,
                "answer": trace.answer,
                "context": trace.context,
                "ground_truth": trace.ground_truth,
                "retrieved_chunks": trace.retrieved_chunks,
                "spans": [s.to_dict() for s in trace.spans],
            }
            mlflow.log_dict(trace_artifact, "trace_data.json")

            # Log suggestions as artifact
            if trace.suggestions:
                mlflow.log_dict(
                    {"suggestions": trace.suggestions},
                    "suggestions.json",
                )

            logger.info(
                f"Logged trace {trace.trace_id[:8]} to MLflow "
                f"(run_id: {run.info.run_id})"
            )

            return run.info.run_id

    def log_metrics(self, trace_id: str, metrics: dict[str, float]):
        """Log additional metrics to an existing run (by trace_id tag)."""
        experiment = mlflow.get_experiment_by_name("default")
        if not experiment:
            return

        runs = self._client.search_runs(
            experiment_ids=[experiment.experiment_id],
            filter_string=f"params.trace_id = '{trace_id}'",
            max_results=1,
        )

        if runs:
            run_id = runs[0].info.run_id
            with mlflow.start_run(run_id=run_id):
                for name, value in metrics.items():
                    mlflow.log_metric(name, value)

    def get_experiment_metrics(
        self, project: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Retrieve metrics for all runs in a project."""
        experiment = mlflow.get_experiment_by_name(project)
        if not experiment:
            return []

        runs = self._client.search_runs(
            experiment_ids=[experiment.experiment_id],
            max_results=limit,
            order_by=["start_time DESC"],
        )

        results = []
        for run in runs:
            results.append(
                {
                    "run_id": run.info.run_id,
                    "trace_id": run.data.params.get("trace_id", ""),
                    "status": run.data.params.get("status", ""),
                    "metrics": dict(run.data.metrics),
                    "params": dict(run.data.params),
                    "start_time": run.info.start_time,
                }
            )

        return results
