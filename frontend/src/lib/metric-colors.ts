// Chart colors, keyed by evaluation-framework `source` (the same field
// MultiSelectPicker groups by) instead of individual metric name. A
// hardcoded per-metric-name map only ever covered the original 6 built-in
// metrics — every metric added by a new adapter fell back to flat gray.
// This scales to any future registry growth with zero enumeration: a new
// source just needs one more palette entry here.
const SOURCE_HUES: Record<string, string[]> = {
  ragas: ["#4f46e5", "#6366f1", "#818cf8", "#a5b4fc"], // indigo — brand
  deepeval: ["#0d9488", "#14b8a6", "#2dd4bf", "#5eead4"], // teal
  arize: ["#c026d3", "#d946ef", "#e879f9", "#f0abfc"], // fuchsia
  mlflow: ["#ea580c", "#f97316", "#fb923c", "#fdba74"], // orange (ready for when that adapter lands)
  custom: ["#64748b", "#94a3b8", "#cbd5e1", "#e2e8f0"], // slate
};

export function getMetricColor(source: string | undefined, indexWithinSource: number): string {
  const palette = SOURCE_HUES[source || "custom"] ?? SOURCE_HUES.custom;
  return palette[indexWithinSource % palette.length];
}

/**
 * Builds a metric-key -> color lookup for a list of metric keys, grouping
 * by `source` first so related metrics (e.g. all DeepEval metrics) get
 * visually related, distinguishable shades instead of one metric owning
 * a hue outright and the rest falling back to gray.
 */
export function buildMetricColorMap(
  metricKeys: string[],
  metricInfo: Record<string, { source?: string }>
): Record<string, string> {
  const countBySource: Record<string, number> = {};
  const colors: Record<string, string> = {};
  for (const key of metricKeys) {
    const source = metricInfo[key]?.source || "ragas";
    const index = countBySource[source] || 0;
    countBySource[source] = index + 1;
    colors[key] = getMetricColor(source, index);
  }
  return colors;
}
