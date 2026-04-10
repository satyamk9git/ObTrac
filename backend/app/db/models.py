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

    # Auth (stored encrypted in production)
    api_key = Column(String, nullable=True)
    api_base = Column(String, nullable=True)
    api_version = Column(String, nullable=True)

    # Provider-specific
    azure_deployment = Column(String, nullable=True)
    vertex_project = Column(String, nullable=True)
    vertex_location = Column(String, nullable=True)
    vertex_credentials = Column(Text, nullable=True)
    aws_region = Column(String, nullable=True)
    aws_access_key = Column(String, nullable=True)
    aws_secret_key = Column(String, nullable=True)

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


class BudgetRecord(Base):
    __tablename__ = "budgets"

    id = Column(String, primary_key=True)
    project = Column(String, index=True, default="default")
    name = Column(String, default="Default Budget")
    period = Column(String, default="monthly")  # daily, weekly, monthly
    amount_usd = Column(Float, default=100.0)
    alert_thresholds = Column(JSON, default=lambda: [50, 80, 100])  # percent thresholds
    is_active = Column(Boolean, default=True)
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
