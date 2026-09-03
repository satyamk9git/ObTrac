// Shared across every place that groups/labels metrics by evaluation
// framework (the trace-detail picker, the dashboard metric grid, chart
// colors) so the taxonomy can't drift between them.
export const METRIC_SOURCE_LABELS: Record<string, string> = {
  ragas: "RAGAS-style",
  deepeval: "DeepEval",
  arize: "Arize Phoenix",
  mlflow: "MLflow",
  custom: "Custom",
};

export const METRIC_SOURCE_ORDER = ["ragas", "deepeval", "arize", "mlflow", "custom"];

export function orderedSources(sources: Iterable<string>): string[] {
  const set = new Set(sources);
  return [
    ...METRIC_SOURCE_ORDER.filter((s) => set.has(s)),
    ...Array.from(set).filter((s) => !METRIC_SOURCE_ORDER.includes(s)),
  ];
}
