"""
Embedder Config API — manage globally-configured embedding models.

These configs are read by the semantic ground truth matcher and any
future RAG-side helpers. One config can be marked as the default; if
none is marked, the matcher falls back to a hardcoded local model.
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.db.database import get_db
from app.db.models import EmbedderConfigRecord

router = APIRouter(prefix="/embedder", tags=["embedder"])


# Known providers + suggested models — purely informational, the user
# can still type any provider/model_id they want.
SUPPORTED_PROVIDERS = {
    "sentence_transformers": {
        "label": "Sentence Transformers (local)",
        "default_model": "all-MiniLM-L6-v2",
        "needs_api_key": False,
        "dimensions_hint": 384,
    },
    "openai": {
        "label": "OpenAI",
        "default_model": "text-embedding-3-small",
        "needs_api_key": True,
        "dimensions_hint": 1536,
    },
    "azure_openai": {
        "label": "Azure OpenAI",
        "default_model": "text-embedding-3-small",
        "needs_api_key": True,
        "dimensions_hint": 1536,
    },
    "cohere": {
        "label": "Cohere",
        "default_model": "embed-english-v3.0",
        "needs_api_key": True,
        "dimensions_hint": 1024,
    },
    "vertex": {
        "label": "Google Vertex AI",
        "default_model": "textembedding-gecko@003",
        "needs_api_key": True,
        "dimensions_hint": 768,
    },
    "huggingface": {
        "label": "Hugging Face Inference API",
        "default_model": "BAAI/bge-large-en-v1.5",
        "needs_api_key": True,
        "dimensions_hint": 1024,
    },
    "ollama": {
        "label": "Ollama (local)",
        "default_model": "nomic-embed-text",
        "needs_api_key": False,
        "dimensions_hint": 768,
    },
}


# ----------------------------- Schemas ------------------------------------

class EmbedderCreate(BaseModel):
    name: str
    provider: str = "sentence_transformers"
    model_id: str = "all-MiniLM-L6-v2"
    dimensions: Optional[int] = None
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    api_version: Optional[str] = None
    azure_deployment: Optional[str] = None
    is_default: bool = False


class EmbedderUpdate(BaseModel):
    provider: Optional[str] = None
    model_id: Optional[str] = None
    dimensions: Optional[int] = None
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    api_version: Optional[str] = None
    azure_deployment: Optional[str] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None


def _to_dict(e: EmbedderConfigRecord, mask_secrets: bool = True) -> dict:
    return {
        "id": e.id,
        "name": e.name,
        "provider": e.provider,
        "model_id": e.model_id,
        "dimensions": e.dimensions,
        "api_key": ("***" if e.api_key and mask_secrets else e.api_key),
        "api_base": e.api_base,
        "api_version": e.api_version,
        "azure_deployment": e.azure_deployment,
        "is_active": e.is_active,
        "is_default": e.is_default,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }


def _clear_other_defaults(db: Session, except_id: Optional[str] = None):
    q = db.query(EmbedderConfigRecord).filter(EmbedderConfigRecord.is_default == True)
    if except_id:
        q = q.filter(EmbedderConfigRecord.id != except_id)
    q.update({"is_default": False})


# ----------------------------- Endpoints ----------------------------------

@router.get("/providers")
def list_providers():
    """Return the catalog of supported embedder providers + suggested models."""
    return {"providers": SUPPORTED_PROVIDERS}


@router.get("")
def list_embedders(db: Session = Depends(get_db)):
    """List all embedder configs."""
    rows = db.query(EmbedderConfigRecord).order_by(EmbedderConfigRecord.created_at.desc()).all()
    return {"embedders": [_to_dict(r) for r in rows]}


@router.get("/default")
def get_default(db: Session = Depends(get_db)):
    """Return the default embedder config, or 404 if none is set."""
    row = (
        db.query(EmbedderConfigRecord)
        .filter(EmbedderConfigRecord.is_default == True, EmbedderConfigRecord.is_active == True)
        .first()
    )
    if not row:
        raise HTTPException(404, "No default embedder configured")
    return _to_dict(row, mask_secrets=False)


@router.post("", status_code=201)
def create_embedder(data: EmbedderCreate, db: Session = Depends(get_db)):
    """Create a new embedder config. If is_default=True, clears other defaults."""
    if data.provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(400, f"Unknown provider '{data.provider}'. See /api/v1/embedder/providers.")

    existing = db.query(EmbedderConfigRecord).filter(EmbedderConfigRecord.name == data.name).first()
    if existing:
        raise HTTPException(409, f"Embedder '{data.name}' already exists")

    if data.is_default:
        _clear_other_defaults(db)

    # If this is the first embedder being created, force it to be the default
    is_first = db.query(EmbedderConfigRecord).count() == 0
    is_default = data.is_default or is_first

    row = EmbedderConfigRecord(
        id=str(uuid.uuid4()),
        name=data.name,
        provider=data.provider,
        model_id=data.model_id,
        dimensions=data.dimensions or SUPPORTED_PROVIDERS[data.provider]["dimensions_hint"],
        api_key=data.api_key,
        api_base=data.api_base,
        api_version=data.api_version,
        azure_deployment=data.azure_deployment,
        is_default=is_default,
        is_active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_dict(row)


@router.put("/{embedder_id}")
def update_embedder(embedder_id: str, data: EmbedderUpdate, db: Session = Depends(get_db)):
    row = db.query(EmbedderConfigRecord).filter(EmbedderConfigRecord.id == embedder_id).first()
    if not row:
        raise HTTPException(404, "Embedder not found")

    update = data.model_dump(exclude_unset=True)
    if update.get("is_default"):
        _clear_other_defaults(db, except_id=embedder_id)

    for k, v in update.items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return _to_dict(row)


@router.delete("/{embedder_id}")
def delete_embedder(embedder_id: str, db: Session = Depends(get_db)):
    row = db.query(EmbedderConfigRecord).filter(EmbedderConfigRecord.id == embedder_id).first()
    if not row:
        raise HTTPException(404, "Embedder not found")
    was_default = row.is_default
    db.delete(row)
    db.commit()

    # If we deleted the default, promote the most-recent remaining one
    if was_default:
        replacement = (
            db.query(EmbedderConfigRecord)
            .filter(EmbedderConfigRecord.is_active == True)
            .order_by(EmbedderConfigRecord.created_at.desc())
            .first()
        )
        if replacement:
            replacement.is_default = True
            db.commit()
    return {"status": "deleted", "id": embedder_id}


@router.post("/{embedder_id}/test")
def test_embedder(embedder_id: str, db: Session = Depends(get_db)):
    """Verify that an embedder config actually works by encoding a tiny string."""
    row = db.query(EmbedderConfigRecord).filter(EmbedderConfigRecord.id == embedder_id).first()
    if not row:
        raise HTTPException(404, "Embedder not found")

    try:
        from app.services.embedder import get_embedding
        vec = get_embedding("test sentence", embedder=row)
        return {
            "status": "ok",
            "dimensions": len(vec),
            "sample": vec[:4] + ["..."] if len(vec) > 4 else vec,
        }
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {e}")
