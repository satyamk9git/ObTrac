"""
SQLite database setup with SQLAlchemy.
"""

import logging
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base
import os

logger = logging.getLogger("obtrac")

DATABASE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
os.makedirs(DATABASE_DIR, exist_ok=True)

DATABASE_URL = f"sqlite:///{os.path.join(DATABASE_DIR, 'obtrac.db')}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Map SQLAlchemy column types to SQLite ALTER TABLE column type strings
def _sqlite_type(col) -> str:
    """Best-effort SQLAlchemy → SQLite type string for ALTER TABLE ADD COLUMN."""
    try:
        return col.type.compile(dialect=engine.dialect)
    except Exception:
        # Fallback by Python type
        py_type = getattr(col.type, "python_type", str)
        return {
            int: "INTEGER",
            float: "REAL",
            bool: "INTEGER",
            bytes: "BLOB",
        }.get(py_type, "TEXT")


def _add_missing_columns():
    """Compare each ORM model against the live SQLite schema and ALTER ADD
    any columns that exist in the model but not in the table. Idempotent.

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
            col_type = _sqlite_type(col)
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
        GroundTruthRecord, AnnotationRecord,
    )
    # 1. Create any tables that don't exist yet
    Base.metadata.create_all(bind=engine)
    # 2. Add any columns that the model has but the existing table is missing
    _add_missing_columns()
