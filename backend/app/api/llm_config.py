"""
LLM Configuration API - CRUD for LLM provider configs.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import uuid

from app.db.database import get_db
from app.db.models import LLMConfigRecord

router = APIRouter(prefix="/llm-configs", tags=["llm-configs"])


class LLMConfigCreate(BaseModel):
    name: str
    provider: str  # openai, azure_openai, anthropic, gemini, vertex_ai, bedrock, ollama, groq, together, huggingface, vllm
    model_id: str
    role: str = "generator"  # generator, judge, master, embedder, custom
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    api_version: Optional[str] = None
    azure_deployment: Optional[str] = None
    vertex_project: Optional[str] = None
    vertex_location: Optional[str] = None
    vertex_credentials: Optional[str] = None
    aws_region: Optional[str] = None
    aws_access_key: Optional[str] = None
    aws_secret_key: Optional[str] = None
    temperature: float = 0.3
    max_tokens: int = 2048
    top_p: float = 1.0
    is_active: bool = True
    cost_per_1k_prompt: float = 0.0
    cost_per_1k_completion: float = 0.0
    use_for_auto_eval: bool = False


class LLMConfigUpdate(BaseModel):
    name: Optional[str] = None
    provider: Optional[str] = None
    model_id: Optional[str] = None
    role: Optional[str] = None
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    api_version: Optional[str] = None
    azure_deployment: Optional[str] = None
    vertex_project: Optional[str] = None
    vertex_location: Optional[str] = None
    vertex_credentials: Optional[str] = None
    aws_region: Optional[str] = None
    aws_access_key: Optional[str] = None
    aws_secret_key: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    is_active: Optional[bool] = None
    cost_per_1k_prompt: Optional[float] = None
    cost_per_1k_completion: Optional[float] = None
    use_for_auto_eval: Optional[bool] = None


def _mask_key(key: str | None) -> str | None:
    if not key:
        return None
    if len(key) <= 8:
        return "****"
    return key[:4] + "****" + key[-4:]


def _config_to_response(config: LLMConfigRecord) -> dict:
    return {
        "id": config.id,
        "name": config.name,
        "provider": config.provider,
        "model_id": config.model_id,
        "role": config.role,
        "api_key_masked": _mask_key(config.api_key),
        "api_base": config.api_base,
        "api_version": config.api_version,
        "azure_deployment": config.azure_deployment,
        "vertex_project": config.vertex_project,
        "vertex_location": config.vertex_location,
        "aws_region": config.aws_region,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "top_p": config.top_p,
        "cost_per_1k_prompt": config.cost_per_1k_prompt or 0,
        "cost_per_1k_completion": config.cost_per_1k_completion or 0,
        "use_for_auto_eval": config.use_for_auto_eval or False,
        "is_active": config.is_active,
        "created_at": config.created_at.isoformat() if config.created_at else None,
        "updated_at": config.updated_at.isoformat() if config.updated_at else None,
    }


@router.post("", status_code=201)
def create_llm_config(data: LLMConfigCreate, db: Session = Depends(get_db)):
    """Create a new LLM configuration."""
    existing = db.query(LLMConfigRecord).filter(LLMConfigRecord.name == data.name).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"LLM config '{data.name}' already exists")

    # Only one LLM can have auto-eval ON
    if data.use_for_auto_eval:
        db.query(LLMConfigRecord).filter(LLMConfigRecord.use_for_auto_eval == True).update({"use_for_auto_eval": False})

    config = LLMConfigRecord(
        id=str(uuid.uuid4()),
        **data.model_dump(),
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return _config_to_response(config)


@router.get("")
def list_llm_configs(
    role: Optional[str] = None,
    provider: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List all LLM configurations."""
    query = db.query(LLMConfigRecord)
    if role:
        query = query.filter(LLMConfigRecord.role == role)
    if provider:
        query = query.filter(LLMConfigRecord.provider == provider)

    configs = query.order_by(LLMConfigRecord.created_at.desc()).all()
    return {"configs": [_config_to_response(c) for c in configs]}


@router.get("/{config_id}")
def get_llm_config(config_id: str, db: Session = Depends(get_db)):
    """Get a specific LLM configuration."""
    config = db.query(LLMConfigRecord).filter(LLMConfigRecord.id == config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="LLM config not found")
    return _config_to_response(config)


@router.put("/{config_id}")
def update_llm_config(config_id: str, data: LLMConfigUpdate, db: Session = Depends(get_db)):
    """Update an LLM configuration."""
    config = db.query(LLMConfigRecord).filter(LLMConfigRecord.id == config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="LLM config not found")

    update_data = data.model_dump(exclude_unset=True)
    # Only one LLM can have auto-eval ON
    if update_data.get("use_for_auto_eval"):
        db.query(LLMConfigRecord).filter(
            LLMConfigRecord.id != config_id,
            LLMConfigRecord.use_for_auto_eval == True,
        ).update({"use_for_auto_eval": False})
    # Don't overwrite sensitive fields with None (user left them blank to keep existing)
    sensitive_fields = {"api_key", "aws_access_key", "aws_secret_key", "vertex_credentials"}
    for key, value in update_data.items():
        if key in sensitive_fields and not value:
            continue  # Keep existing value
        setattr(config, key, value)

    db.commit()
    db.refresh(config)
    return _config_to_response(config)


@router.delete("/{config_id}")
def delete_llm_config(config_id: str, db: Session = Depends(get_db)):
    """Delete an LLM configuration."""
    config = db.query(LLMConfigRecord).filter(LLMConfigRecord.id == config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="LLM config not found")
    db.delete(config)
    db.commit()
    return {"status": "deleted", "id": config_id}


@router.post("/{config_id}/test")
def test_llm_connection(config_id: str, db: Session = Depends(get_db)):
    """Test connectivity to an LLM."""
    config = db.query(LLMConfigRecord).filter(LLMConfigRecord.id == config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="LLM config not found")

    from obtrac_sdk.llm_gateway import LLMGateway
    from obtrac_sdk.models import LLMConfig, LLMProvider, LLMRole

    gateway = LLMGateway()
    llm_config = LLMConfig(
        name=config.name,
        provider=LLMProvider(config.provider),
        model_id=config.model_id,
        role=LLMRole(config.role),
        api_key=config.api_key,
        api_base=config.api_base,
        api_version=config.api_version,
        azure_deployment=config.azure_deployment,
        vertex_project=config.vertex_project,
        vertex_location=config.vertex_location,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
    )
    gateway.register(llm_config)
    result = gateway.test_connection(config.name)
    return result
