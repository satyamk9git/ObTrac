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
