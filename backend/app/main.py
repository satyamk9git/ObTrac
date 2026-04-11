"""
ObTrac Backend - FastAPI Application
"""

import math
import json
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
    description="ObTrac - Open Source RAG Observability & Evaluation Framework",
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


@app.on_event("startup")
def startup_event():
    logger.info("Initializing ObTrac database...")
    init_db()
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
