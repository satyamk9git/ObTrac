"use client";

interface Span {
  span_id: string;
  parent_span_id: string | null;
  name: string;
  span_type: string;
  status: string;
  latency_ms: number;
  inputs: Record<string, any>;
  outputs: Record<string, any>;
  error: string | null;
  tokens: Record<string, number>;
  cost_usd: number;
  model: string | null;
  tool_calls?: { id?: string; name: string; arguments: any }[] | null;
  tool_name?: string | null;
  tool_call_id?: string | null;
  tool_args?: Record<string, any> | null;
  tool_result?: any;
}

function SpanNode({ span, children }: { span: Span; children: Span[] }) {
  const typeColors: Record<string, string> = {
    retrieval: "bg-blue-500/15 text-blue-400",
    generation: "bg-purple-500/15 text-purple-400",
    embedding: "bg-green-500/15 text-green-400",
    reranking: "bg-orange-500/15 text-orange-400",
    tool_call: "bg-yellow-500/15 text-yellow-400",
    agent: "bg-pink-500/15 text-pink-400",
    planning: "bg-cyan-500/15 text-cyan-400",
    custom: "bg-gray-500/15 text-gray-400",
  };

  const childSpans = children.filter((s) => s.parent_span_id === span.span_id);

  return (
    <div className="ml-4 border-l border-[#2d3348] pl-4 py-2 animate-slide-in">
      <div className="flex items-center gap-2 mb-1">
        <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${typeColors[span.span_type] || typeColors.custom}`}>
          {span.span_type}
        </span>
        <span className="font-medium text-sm text-gray-200">{span.name}</span>
        <span className={`text-[10px] ${span.status === "success" ? "text-green-400" : "text-red-400"}`}>
          {span.status}
        </span>
        <span className="text-[10px] text-gray-500">{(span.latency_ms || 0).toFixed(0)}ms</span>
        {span.model && (
          <span className="text-[10px] bg-[#252a3f] text-gray-400 px-1.5 py-0.5 rounded">{span.model}</span>
        )}
        {span.tool_name && (
          <span className="text-[10px] bg-yellow-500/15 text-yellow-400 px-1.5 py-0.5 rounded font-mono">
            🔧 {span.tool_name}
          </span>
        )}
        {span.tool_calls && span.tool_calls.length > 0 && (
          <span className="text-[10px] bg-yellow-500/15 text-yellow-400 px-1.5 py-0.5 rounded">
            requested {span.tool_calls.length} tool call{span.tool_calls.length !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      {span.error && (
        <div className="text-xs text-red-400 bg-red-500/10 p-2 rounded mt-1 border border-red-500/20">
          {span.error}
        </div>
      )}

      {span.tool_name && (
        <div className="text-xs mt-1 bg-yellow-500/5 border border-yellow-500/20 rounded p-2 space-y-1">
          <div>
            <span className="font-medium text-yellow-400">Tool: </span>
            <span className="text-gray-300 font-mono">{span.tool_name}</span>
          </div>
          {span.tool_args && Object.keys(span.tool_args).length > 0 && (
            <div>
              <span className="font-medium text-gray-400">Args: </span>
              <span className="text-gray-500 font-mono">{JSON.stringify(span.tool_args)}</span>
            </div>
          )}
          {span.tool_result != null && (
            <div>
              <span className="font-medium text-gray-400">Result: </span>
              <span className="text-gray-500">{String(span.tool_result).substring(0, 300)}</span>
            </div>
          )}
        </div>
      )}

      {span.tool_calls && span.tool_calls.length > 0 && (
        <div className="text-xs mt-1 bg-yellow-500/5 border border-yellow-500/20 rounded p-2 space-y-1">
          <span className="font-medium text-yellow-400">Requested tool calls:</span>
          {span.tool_calls.map((c, i) => (
            <div key={c.id || i} className="text-gray-500 font-mono pl-2">
              {c.name}({JSON.stringify(c.arguments)})
            </div>
          ))}
        </div>
      )}

      <details className="text-xs mt-1">
        <summary className="cursor-pointer text-gray-500 hover:text-gray-300">Details</summary>
        <div className="mt-1 space-y-1 bg-[#161927] p-2 rounded border border-[#2d3348]">
          {Object.keys(span.inputs || {}).length > 0 && (
            <div>
              <span className="font-medium text-gray-400">Input: </span>
              <pre className="text-gray-500 whitespace-pre-wrap max-h-32 overflow-auto">
                {JSON.stringify(span.inputs, null, 2).substring(0, 500)}
              </pre>
            </div>
          )}
          {Object.keys(span.outputs || {}).length > 0 && (
            <div>
              <span className="font-medium text-gray-400">Output: </span>
              <pre className="text-gray-500 whitespace-pre-wrap max-h-32 overflow-auto">
                {JSON.stringify(span.outputs, null, 2).substring(0, 500)}
              </pre>
            </div>
          )}
          {Object.keys(span.tokens || {}).length > 0 && (
            <div className="text-gray-500">
              Tokens: prompt={span.tokens.prompt || 0}, completion={span.tokens.completion || 0} | Cost: ${(span.cost_usd || 0).toFixed(6)}
            </div>
          )}
        </div>
      </details>

      {childSpans.map((child) => (
        <SpanNode key={child.span_id} span={child} children={children} />
      ))}
    </div>
  );
}

export default function SpanTree({ spans }: { spans: Span[] }) {
  const rootSpans = spans.filter((s) => !s.parent_span_id);

  if (spans.length === 0) {
    return <p className="text-sm text-gray-500">No spans recorded</p>;
  }

  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-gray-300 mb-2">Span Tree</h3>
      {(rootSpans.length > 0 ? rootSpans : spans).map((span) => (
        <SpanNode key={span.span_id} span={span} children={spans} />
      ))}
    </div>
  );
}
