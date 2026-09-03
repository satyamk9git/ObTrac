"""
ObTrac Backend - FastAPI Application
"""

import math
import json
import os
import secrets
import traceback
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import logging


def _clean_nan(obj):
    """Recursively replace NaN/Inf floats with None in dicts/lists."""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_nan(v) for v in obj]
    return obj


class NaNSafeJSONResponse(JSONResponse):
    """JSON response that converts NaN/Inf to None before serializing."""

    def render(self, content) -> bytes:
        cleaned = _clean_nan(content)
        return json.dumps(
            cleaned,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

from app.core.config import settings
from app.db.database import init_db
from app.api import traces, metrics, llm_config, resources, suggestions, evaluation, analytics, sql_editor, compare, annotations, sessions, prompts, budgets, alerts, explain, embedder

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("obtrac")

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Cortexa - Open Source RAG Observability & Evaluation Framework",
    docs_url="/docs",
    redoc_url="/redoc",
    default_response_class=NaNSafeJSONResponse,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3100",
        "http://localhost:8501",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3100",
        "http://127.0.0.1:8501",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- API key auth (off by default) ---------------------------------------
# ObTrac ships with no auth by default, matching its self-hosted /
# localhost-first design — but that means anyone who can reach the port has
# full read/write access. Setting OBTRAC_API_KEY turns on a gate: every
# /api/* request must send `Authorization: Bearer <key>`. /health, /docs,
# and / stay open so basic liveness checks and API docs don't need a key.
OBTRAC_API_KEY = os.environ.get("OBTRAC_API_KEY", "").strip()


@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    if OBTRAC_API_KEY and request.url.path.startswith("/api/"):
        auth_header = request.headers.get("authorization", "")
        provided = auth_header[7:] if auth_header.lower().startswith("bearer ") else ""
        if not provided or not secrets.compare_digest(provided, OBTRAC_API_KEY):
            return JSONResponse(
                status_code=401,
                content={
                    "error": "Unauthorized",
                    "message": "Missing or invalid API key. Send 'Authorization: Bearer <OBTRAC_API_KEY>'.",
                },
            )
    return await call_next(request)


def _clear_orphaned_eval_jobs():
    """Eval jobs run in daemon threads inside the backend process. If the
    process dies or gets killed (crash, restart, `obtrac stop`) while a job
    is mid-flight, that thread dies with it — but the job's DB row is left
    at status='running' or 'queued' forever, since nothing else was ever
    going to mark it finished. The dashboard's "resume an in-flight job's
    spinner on page load" feature then shows that stuck job as perpetually
    running, indefinitely, even though nothing is actually processing it.
    A job can't legitimately survive past this process's own restart, so
    anything still queued/running at boot is from a run this process never
    finished — mark it failed rather than leaving it stuck."""
    from app.db.database import SessionLocal
    from app.db.models import EvalJobRecord
    from datetime import datetime

    db = SessionLocal()
    try:
        stuck = db.query(EvalJobRecord).filter(EvalJobRecord.status.in_(["queued", "running"])).all()
        for job in stuck:
            job.status = "failed"
            job.error = "Interrupted by backend restart — no worker thread survived the process restart to finish this job."
            job.finished_at = datetime.utcnow()
        if stuck:
            db.commit()
            logger.info(f"Startup cleanup: marked {len(stuck)} orphaned eval job(s) as failed (interrupted by restart)")
    finally:
        db.close()


@app.on_event("startup")
def startup_event():
    logger.info("Initializing ObTrac database...")
    init_db()
    _clear_orphaned_eval_jobs()
    if OBTRAC_API_KEY:
        logger.info("API key auth is ENABLED — all /api/* requests require Authorization: Bearer <key>")
    else:
        logger.warning(
            "OBTRAC_API_KEY is not set — the API is running WITHOUT authentication. "
            "Fine for local-only use; set OBTRAC_API_KEY before exposing this instance "
            "beyond localhost or a trusted private network."
        )
    logger.info("ObTrac backend started successfully")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Return the actual error type + message in 500 responses so the SDK
    surfaces a useful warning instead of generic 'Internal Server Error'."""
    tb = traceback.format_exc()
    logger.error(f"Unhandled error on {request.method} {request.url.path}:\n{tb}")
    return JSONResponse(
        status_code=500,
        content={
            "error": type(exc).__name__,
            "message": str(exc),
            "path": request.url.path,
        },
    )


@app.get("/")
def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}


# Register routers
app.include_router(traces.router, prefix="/api/v1")
app.include_router(metrics.router, prefix="/api/v1")
app.include_router(llm_config.router, prefix="/api/v1")
app.include_router(resources.router, prefix="/api/v1")
app.include_router(suggestions.router, prefix="/api/v1")
app.include_router(evaluation.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")
app.include_router(sql_editor.router, prefix="/api/v1")
app.include_router(compare.router, prefix="/api/v1")
app.include_router(annotations.router, prefix="/api/v1")
app.include_router(sessions.router, prefix="/api/v1")
app.include_router(prompts.router, prefix="/api/v1")
app.include_router(budgets.router, prefix="/api/v1")
app.include_router(alerts.router, prefix="/api/v1")
app.include_router(explain.router, prefix="/api/v1")
app.include_router(embedder.router, prefix="/api/v1")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
