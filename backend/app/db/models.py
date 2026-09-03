"""
SQLAlchemy ORM models for ObTrac database.
"""

from sqlalchemy import (
    Column,
    String,
    Float,
    Integer,
    Boolean,
    DateTime,
    Text,
    JSON,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from datetime import datetime

from app.db.database import Base
from app.core.crypto import EncryptedString


class ProjectRecord(Base):
    """User-created project. Projects can also exist implicitly as the
    `project` string on traces/prompts/etc — this table just gives the user
    a way to create a project up-front (before any traces are logged) so
    it shows in dropdowns and they can attach prompts/datasets to it."""
    __tablename__ = "projects"

    name = Column(String, primary_key=True)
    description = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class TraceRecord(Base):
    __tablename__ = "traces"

    trace_id = Column(String, primary_key=True)
    project = Column(String, index=True, default="default")
    name = Column(String, default="")
    user = Column(String, default="", index=True)
    session_id = Column(String, default="", index=True)
    eval_status = Column(String, default="none")  # none, pending, running, completed, failed
    prompt_versions_used = Column(JSON, default=list)  # list of {prompt_name, version}
    status = Column(String, default="running")
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    total_latency_ms = Column(Float, default=0.0)
    total_cost_usd = Column(Float, default=0.0)
    total_tokens = Column(JSON, default=dict)

    # RAG data
    query = Column(Text, default="")
    context = Column(Text, default="")
    answer = Column(Text, default="")
    ground_truth = Column(Text, nullable=True)
    retrieved_chunks = Column(JSON, default=list)

    # Evaluation results
    metrics = Column(JSON, default=dict)
    suggestions = Column(JSON, default=list)
    metadata_json = Column(JSON, default=dict)

    created_at = Column(DateTime, default=datetime.utcnow)

    spans = relationship("SpanRecord", back_populates="trace", cascade="all, delete-orphan")


class SpanRecord(Base):
    __tablename__ = "spans"

    span_id = Column(String, primary_key=True)
    trace_id = Column(String, ForeignKey("traces.trace_id"), index=True)
    parent_span_id = Column(String, nullable=True)
    name = Column(String, default="")
    span_type = Column(String, default="custom")
    status = Column(String, default="running")
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    latency_ms = Column(Float, default=0.0)
    inputs = Column(JSON, default=dict)
    outputs = Column(JSON, default=dict)
    metadata_json = Column(JSON, default=dict)
    error = Column(Text, nullable=True)
    tokens = Column(JSON, default=dict)
    cost_usd = Column(Float, default=0.0)
    model = Column(String, nullable=True)

    trace = relationship("TraceRecord", back_populates="spans")


class LLMConfigRecord(Base):
    __tablename__ = "llm_configs"

    id = Column(String, primary_key=True)
    name = Column(String, unique=True, index=True)
    provider = Column(String, default="openai")
    model_id = Column(String, default="")
    role = Column(String, default="generator")

    # Auth — encrypted at rest (see app/core/crypto.py)
    api_key = Column(EncryptedString, nullable=True)
    api_base = Column(String, nullable=True)
    api_version = Column(String, nullable=True)

    # Provider-specific
    azure_deployment = Column(String, nullable=True)
    vertex_project = Column(String, nullable=True)
    vertex_location = Column(String, nullable=True)
    vertex_credentials = Column(EncryptedString, nullable=True)
    aws_region = Column(String, nullable=True)
    aws_access_key = Column(EncryptedString, nullable=True)
    aws_secret_key = Column(EncryptedString, nullable=True)

    # Params
    temperature = Column(Float, default=0.3)
    max_tokens = Column(Integer, default=2048)
    top_p = Column(Float, default=1.0)
    is_active = Column(Boolean, default=True)

    # Cost per 1K tokens (USD)
    cost_per_1k_prompt = Column(Float, default=0.0)
    cost_per_1k_completion = Column(Float, default=0.0)

    # Auto-eval: only one LLM should have this ON
    use_for_auto_eval = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EvalJobRecord(Base):
    """An evaluation run that may take a while. Allows the frontend to fire
    and forget — the eval continues in a backend daemon thread even if the
    user navigates to a different page or closes the browser.

    Status lifecycle: queued → running → completed | failed | cancelled
    """
    __tablename__ = "eval_jobs"

    id = Column(String, primary_key=True)
    trace_id = Column(String, index=True)
    project = Column(String, index=True, default="default")
    status = Column(String, default="queued")  # queued, running, completed, failed, cancelled
    metrics = Column(JSON, default=list)        # ["faithfulness", ...]
    judge_llm_config_ids = Column(JSON, default=list)
    dataset_name = Column(String, nullable=True)
    ground_truth = Column(Text, nullable=True)

    result = Column(JSON, nullable=True)        # full multi-LLM result payload when done
    error = Column(Text, nullable=True)
    progress_message = Column(String, default="")  # e.g. "Running faithfulness on Az Judge..."

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)


class EmbedderConfigRecord(Base):
    """Globally-configured embedding model. Used by semantic ground truth
    matching, retrieval helpers, etc. Mirrors the LLM Config pattern: a
    small set of named configs, one marked as default."""
    __tablename__ = "embedder_configs"

    id = Column(String, primary_key=True)
    name = Column(String, unique=True, index=True)
    provider = Column(String, default="sentence_transformers")
    # Common values: sentence_transformers, openai, azure_openai, cohere, vertex, huggingface, ollama
    model_id = Column(String, default="all-MiniLM-L6-v2")
    dimensions = Column(Integer, nullable=True)  # informational, e.g. 384 for MiniLM, 1536 for ada-002

    api_key = Column(EncryptedString, nullable=True)  # encrypted at rest (see app/core/crypto.py)
    api_base = Column(String, nullable=True)
    api_version = Column(String, nullable=True)
    azure_deployment = Column(String, nullable=True)

    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)  # only one at a time
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class BudgetRecord(Base):
    __tablename__ = "budgets"

    id = Column(String, primary_key=True)
    project = Column(String, index=True, default="default")
    name = Column(String, default="Default Budget")
    period = Column(String, default="monthly")  # daily, weekly, monthly
    amount_usd = Column(Float, default=100.0)
    alert_thresholds = Column(JSON, default=lambda: [50, 80, 100])  # percent thresholds
    is_active = Column(Boolean, default=True)

    # Explicit per-budget alert channel routing. List of AlertChannelRecord IDs.
    # Empty list = no notifications fire for this budget.
    alert_channel_ids = Column(JSON, default=list)

    # De-dup state — prevents firing the same threshold over and over as
    # additional traces land on top of an already-crossed threshold.
    # Reset when the budget's period rolls over (handled in check_budget_alerts).
    last_fired_threshold = Column(Integer, nullable=True)
    last_fired_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AlertChannelRecord(Base):
    __tablename__ = "alert_channels"

    id = Column(String, primary_key=True)
    name = Column(String, default="")
    channel_type = Column(String, default="webhook")  # webhook, slack, email
    config = Column(JSON, default=dict)  # {"url": "...", "headers": {}}
    is_active = Column(Boolean, default=True)
    project = Column(String, default="all")  # "all" or specific project
    triggers = Column(JSON, default=list)  # list of event types: budget_50, budget_80, budget_100, metric_low, error_spike
    created_at = Column(DateTime, default=datetime.utcnow)


class AlertHistoryRecord(Base):
    __tablename__ = "alert_history"

    id = Column(String, primary_key=True)
    channel_id = Column(String, ForeignKey("alert_channels.id"), index=True)
    project = Column(String, index=True, default="default")
    event_type = Column(String, default="")  # budget_50, budget_100, metric_low, etc.
    severity = Column(String, default="info")  # info, warning, critical
    message = Column(Text, default="")
    payload = Column(JSON, default=dict)
    delivered = Column(Boolean, default=False)
    response_status = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PromptRecord(Base):
    __tablename__ = "prompts"

    id = Column(String, primary_key=True)
    project = Column(String, index=True, default="default")
    name = Column(String, index=True)  # unique per project
    description = Column(Text, default="")
    tags = Column(JSON, default=list)
    created_by = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    versions = relationship("PromptVersionRecord", back_populates="prompt", cascade="all, delete-orphan")


class PromptVersionRecord(Base):
    __tablename__ = "prompt_versions"

    id = Column(String, primary_key=True)
    prompt_id = Column(String, ForeignKey("prompts.id"), index=True)
    version = Column(Integer, default=1)
    template = Column(Text, default="")
    variables = Column(JSON, default=list)  # auto-extracted from template
    model = Column(String, nullable=True)
    temperature = Column(Float, nullable=True)
    is_active = Column(Boolean, default=False)  # only one version active at a time
    commit_message = Column(Text, default="")
    created_by = Column(String, default="")
    metadata_json = Column(JSON, default=dict)  # e.g. {"merged_from": [2, 3], "merged_by_llm": "gpt-4o"}
    created_at = Column(DateTime, default=datetime.utcnow)

    prompt = relationship("PromptRecord", back_populates="versions")


class AnnotationRecord(Base):
    __tablename__ = "annotations"

    id = Column(String, primary_key=True)
    trace_id = Column(String, ForeignKey("traces.trace_id"), index=True)
    rating = Column(String, default="")  # thumbs_up, thumbs_down, neutral
    label = Column(String, default="")  # correct, incorrect, partial, hallucination, irrelevant
    notes = Column(Text, default="")
    annotated_by = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class GroundTruthRecord(Base):
    __tablename__ = "ground_truths"

    id = Column(String, primary_key=True)
    project = Column(String, index=True, default="default")
    dataset_name = Column(String, default="")
    question = Column(Text, default="")
    ground_truth = Column(Text, default="")
    context = Column(Text, nullable=True)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
