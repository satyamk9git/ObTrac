"""
Database setup with SQLAlchemy. SQLite by default (zero setup, matches
ObTrac's self-hosted-first design); set DATABASE_URL to point at Postgres
instead for higher write concurrency than SQLite can offer.

Postgres support here is implemented (dialect-agnostic engine config, the
auto-migration path compiles column types via SQLAlchemy's dialect
compiler rather than hardcoded SQLite type strings) but has not been
exercised against a live Postgres server in this codebase's test history —
verify against a disposable database before relying on it for anything you
can't afford to lose. Needs `pip install psycopg2-binary` (not bundled by
default, to avoid forcing a C-extension build for the common SQLite-only
case).
"""

import logging
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base
import os

logger = logging.getLogger("obtrac")

DATABASE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
os.makedirs(DATABASE_DIR, exist_ok=True)

DATABASE_URL = os.environ.get("DATABASE_URL") or f"sqlite:///{os.path.join(DATABASE_DIR, 'obtrac.db')}"
IS_SQLITE = DATABASE_URL.startswith("sqlite")

_connect_args = {"check_same_thread": False} if IS_SQLITE else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

if not IS_SQLITE:
    logger.info(f"Using external database (dialect: {engine.dialect.name})")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Map SQLAlchemy column types to the active dialect's ALTER TABLE column
# type string (works for SQLite or Postgres — whichever DATABASE_URL points at)
def _compiled_column_type(col) -> str:
    """Best-effort SQLAlchemy -> SQL type string for ALTER TABLE ADD COLUMN,
    compiled against whichever dialect is actually active."""
    try:
        return col.type.compile(dialect=engine.dialect)
    except Exception:
        # Fallback by Python type — SQLite is loosely typed so these type
        # affinities work there; on Postgres BOOLEAN/BYTEA are the correct
        # names (not SQLite's INTEGER/BLOB), so branch on dialect.
        py_type = getattr(col.type, "python_type", str)
        if IS_SQLITE:
            return {int: "INTEGER", float: "REAL", bool: "INTEGER", bytes: "BLOB"}.get(py_type, "TEXT")
        return {int: "INTEGER", float: "DOUBLE PRECISION", bool: "BOOLEAN", bytes: "BYTEA"}.get(py_type, "TEXT")


def _add_missing_columns():
    """Compare each ORM model against the live schema and ALTER ADD any
    columns that exist in the model but not in the table. Idempotent.

    This is a lightweight in-place migration so existing installs upgrading
    to a newer schema don't crash on inserts referencing new columns. It
    only ADDS columns — it never drops, renames, or changes types."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    for table_name, table in Base.metadata.tables.items():
        if table_name not in existing_tables:
            continue  # create_all will handle brand-new tables

        existing_cols = {c["name"] for c in inspector.get_columns(table_name)}
        for col in table.columns:
            if col.name in existing_cols:
                continue
            col_type = _compiled_column_type(col)
            nullable = "" if col.nullable else " NOT NULL"
            default_clause = ""
            if col.default is not None and getattr(col.default, "is_scalar", False):
                # Only inline simple scalar defaults (string/int/bool literals)
                default_val = col.default.arg
                if isinstance(default_val, bool):
                    default_clause = f" DEFAULT {1 if default_val else 0}"
                elif isinstance(default_val, (int, float)):
                    default_clause = f" DEFAULT {default_val}"
                elif isinstance(default_val, str):
                    escaped = default_val.replace("'", "''")
                    default_clause = f" DEFAULT '{escaped}'"
            ddl = f'ALTER TABLE "{table_name}" ADD COLUMN "{col.name}" {col_type}{nullable}{default_clause}'
            try:
                with engine.begin() as conn:
                    conn.execute(text(ddl))
                logger.info(f"Schema migration: added {table_name}.{col.name}")
            except Exception as e:
                logger.warning(f"Schema migration: could not add {table_name}.{col.name}: {e}")


def init_db():
    from app.db.models import (
        ProjectRecord, TraceRecord, SpanRecord, LLMConfigRecord,
        EmbedderConfigRecord, EvalJobRecord, GroundTruthRecord, AnnotationRecord,
    )
    # 1. Create any tables that don't exist yet
    Base.metadata.create_all(bind=engine)
    # 2. Add any columns that the model has but the existing table is missing
    _add_missing_columns()
