"use client";

interface MetricCardProps {
  name: string;
  value: number;
  threshold?: number;
  description?: string;
}

export default function MetricCard({
  name,
  value,
  threshold = 0.7,
  description,
}: MetricCardProps) {
  const getScoreClass = (v: number) => {
    if (v >= 0.8) return "score-good";
    if (v >= threshold) return "score-warning";
    return "score-bad";
  };

  const getBarColor = (v: number) => {
    if (v >= 0.8) return "bg-green-500";
    if (v >= threshold) return "bg-yellow-500";
    return "bg-red-500";
  };

  return (
    <div className="metric-card">
      <div className="flex justify-between items-start mb-2">
        <h3 className="text-sm font-medium text-gray-600 capitalize">
          {name.replace(/_/g, " ")}
        </h3>
        <span className={`text-2xl ${getScoreClass(value)}`}>
          {(value * 100).toFixed(1)}%
        </span>
      </div>

      <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
        <div
          className={`h-2 rounded-full ${getBarColor(value)} transition-all`}
          style={{ width: `${Math.min(value * 100, 100)}%` }}
        />
      </div>

      {description && (
        <p className="text-xs text-gray-500 mt-2">{description}</p>
      )}

      <div className="flex items-center mt-2">
        <span className="text-xs text-gray-400">
          Threshold: {(threshold * 100).toFixed(0)}%
        </span>
        {value < threshold && (
          <span className="ml-2 text-xs text-red-500 font-medium">
            Below threshold
          </span>
        )}
      </div>
    </div>
  );
}
