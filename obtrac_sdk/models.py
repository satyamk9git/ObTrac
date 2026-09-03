"""
Data models for ObTrac traces, spans, and metrics.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from enum import Enum
import uuid


class SpanType(str, Enum):
    RETRIEVAL = "retrieval"
    GENERATION = "generation"
    EMBEDDING = "embedding"
    RERANKING = "reranking"
    TOOL_CALL = "tool_call"
    AGENT = "agent"
    PLANNING = "planning"
    CUSTOM = "custom"


class SpanStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    RUNNING = "running"


class LLMRole(str, Enum):
    GENERATOR = "generator"
    JUDGE = "judge"
    MASTER = "master"
    EMBEDDER = "embedder"
    CUSTOM = "custom"


class LLMProvider(str, Enum):
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    VERTEX_AI = "vertex_ai"
    BEDROCK = "bedrock"
    OLLAMA = "ollama"
    GROQ = "groq"
    TOGETHER = "together"
    HUGGINGFACE = "huggingface"
    VLLM = "vllm"
    CUSTOM = "custom"


@dataclass
class Span:
    span_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str = ""
    parent_span_id: str | None = None
    name: str = ""
    span_type: SpanType = SpanType.CUSTOM
    status: SpanStatus = SpanStatus.RUNNING
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: datetime | None = None
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    latency_ms: float = 0.0
    tokens: dict[str, int] = field(default_factory=dict)
    cost_usd: float = 0.0
    model: str | None = None
    # Tool-call fields. `tool_calls` is for a GENERATION span that
    # *requested* one or more calls (from the LLM response's own
    # tool_calls, auto-captured by llm_gateway.call()); `tool_name`/
    # `tool_call_id`/`tool_args`/`tool_result` are for a TOOL_CALL span
    # that *executed* one — a single LLM turn can request several tool
    # calls before any of them actually run, so these are deliberately
    # separate rather than reusing one field for both.
    tool_calls: list[dict] | None = None
    tool_name: str | None = None
    tool_call_id: str | None = None
    tool_args: dict[str, Any] | None = None
    tool_result: Any | None = None

    def finish(self, outputs: dict = None, error: str = None):
        self.end_time = datetime.utcnow()
        self.latency_ms = (self.end_time - self.start_time).total_seconds() * 1000
        if outputs:
            self.outputs = outputs
        if error:
            self.error = error
            self.status = SpanStatus.ERROR
        else:
            self.status = SpanStatus.SUCCESS

    def to_dict(self) -> dict:
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "span_type": self.span_type.value,
            "status": self.status.value,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "metadata": self.metadata,
            "error": self.error,
            "latency_ms": self.latency_ms,
            "tokens": self.tokens,
            "cost_usd": self.cost_usd,
            "model": self.model,
            "tool_calls": self.tool_calls,
            "tool_name": self.tool_name,
            "tool_call_id": self.tool_call_id,
            "tool_args": self.tool_args,
            "tool_result": self.tool_result,
        }


@dataclass
class Trace:
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    project: str = ""
    name: str = ""
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: datetime | None = None
    status: SpanStatus = SpanStatus.RUNNING
    total_latency_ms: float = 0.0
    total_cost_usd: float = 0.0
    total_tokens: dict[str, int] = field(default_factory=dict)
    spans: list[Span] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    suggestions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    # User & session tracking
    user: str = ""
    session_id: str = ""

    # RAG-specific fields captured by @observe
    query: str = ""
    retrieved_chunks: list[dict] = field(default_factory=list)
    context: str = ""
    answer: str = ""
    ground_truth: str | None = None

    def finish(self):
        self.end_time = datetime.utcnow()
        self.total_latency_ms = (self.end_time - self.start_time).total_seconds() * 1000
        self.total_cost_usd = sum(s.cost_usd for s in self.spans)
        prompt_tokens = sum(s.tokens.get("prompt", 0) for s in self.spans)
        completion_tokens = sum(s.tokens.get("completion", 0) for s in self.spans)
        self.total_tokens = {"prompt": prompt_tokens, "completion": completion_tokens}
        if any(s.status == SpanStatus.ERROR for s in self.spans):
            self.status = SpanStatus.ERROR
        else:
            self.status = SpanStatus.SUCCESS

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "project": self.project,
            "name": self.name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "status": self.status.value,
            "total_latency_ms": self.total_latency_ms,
            "total_cost_usd": self.total_cost_usd,
            "total_tokens": self.total_tokens,
            "spans": [s.to_dict() for s in self.spans],
            "metrics": self.metrics,
            "suggestions": self.suggestions,
            "metadata": self.metadata,
            "user": self.user,
            "session_id": self.session_id,
            "query": self.query,
            "retrieved_chunks": self.retrieved_chunks,
            "context": self.context,
            "answer": self.answer,
            "ground_truth": self.ground_truth,
        }


@dataclass
class LLMConfig:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    provider: LLMProvider = LLMProvider.OPENAI
    model_id: str = ""
    role: LLMRole = LLMRole.GENERATOR
    api_key: str | None = None
    api_base: str | None = None
    api_version: str | None = None
    # Azure
    azure_deployment: str | None = None
    # Vertex AI
    vertex_project: str | None = None
    vertex_location: str | None = None
    vertex_credentials: str | None = None
    # AWS Bedrock
    aws_region: str | None = None
    aws_access_key: str | None = None
    aws_secret_key: str | None = None
    # Params
    temperature: float = 0.3
    max_tokens: int = 2048
    top_p: float = 1.0
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "provider": self.provider.value,
            "model_id": self.model_id,
            "role": self.role.value,
            "api_base": self.api_base,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class EvalResult:
    trace_id: str = ""
    metrics: dict[str, float] = field(default_factory=dict)
    suggestions: list[str] = field(default_factory=list)
    judge_model: str = ""
    evaluated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "metrics": self.metrics,
            "suggestions": self.suggestions,
            "judge_model": self.judge_model,
            "evaluated_at": self.evaluated_at.isoformat(),
        }
