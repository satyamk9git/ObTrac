"""
Prompts API — versioned prompt registry.
"""

import re
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import Optional

from app.db.database import get_db
from app.db.models import PromptRecord, PromptVersionRecord

router = APIRouter(prefix="/prompts", tags=["prompts"])


# ========================================
# Schemas
# ========================================

class PromptCreate(BaseModel):
    name: str
    description: str = ""
    tags: list[str] = []
    template: str
    model: Optional[str] = None
    temperature: Optional[float] = None
    commit_message: str = "Initial version"
    created_by: str = ""
    project: str = "default"


class VersionCreate(BaseModel):
    template: str
    model: Optional[str] = None
    temperature: Optional[float] = None
    commit_message: str = ""
    created_by: str = ""


class PromptUpdate(BaseModel):
    description: Optional[str] = None
    tags: Optional[list[str]] = None


# ========================================
# Helpers
# ========================================

def _extract_variables(template: str) -> list[str]:
    """Extract {variable} names from a template string."""
    pattern = re.compile(r"\{(\w+)\}")
    return list(set(pattern.findall(template)))


def _version_to_dict(v: PromptVersionRecord) -> dict:
    return {
        "id": v.id,
        "prompt_id": v.prompt_id,
        "version": v.version,
        "template": v.template,
        "variables": v.variables or [],
        "model": v.model,
        "temperature": v.temperature,
        "is_active": v.is_active,
        "commit_message": v.commit_message,
        "created_by": v.created_by,
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }


def _prompt_to_dict(p: PromptRecord, include_versions: bool = False) -> dict:
    latest = max(p.versions, key=lambda v: v.version) if p.versions else None
    active = next((v for v in p.versions if v.is_active), latest)

    data = {
        "id": p.id,
        "project": p.project,
        "name": p.name,
        "description": p.description,
        "tags": p.tags or [],
        "created_by": p.created_by,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        "latest_version": latest.version if latest else 0,
        "active_version": active.version if active else 0,
        "version_count": len(p.versions),
    }

    if include_versions:
        data["versions"] = [_version_to_dict(v) for v in sorted(p.versions, key=lambda x: -x.version)]
        if active:
            data["active"] = _version_to_dict(active)

    return data


# ========================================
# Endpoints
# ========================================

@router.get("")
def list_prompts(
    project: str = Query("all"),
    tag: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List all prompts in a project."""
    query = db.query(PromptRecord)
    if project != "all":
        query = query.filter(PromptRecord.project == project)
    prompts = query.order_by(PromptRecord.updated_at.desc()).all()

    result = [_prompt_to_dict(p) for p in prompts]
    if tag:
        result = [p for p in result if tag in (p.get("tags") or [])]
    return {"prompts": result}


@router.post("", status_code=201)
def create_prompt(data: PromptCreate, db: Session = Depends(get_db)):
    """Create a new prompt with its first version."""
    existing = (
        db.query(PromptRecord)
        .filter(PromptRecord.project == data.project, PromptRecord.name == data.name)
        .first()
    )
    if existing:
        raise HTTPException(409, f"Prompt '{data.name}' already exists in project '{data.project}'")

    prompt = PromptRecord(
        id=str(uuid.uuid4()),
        project=data.project,
        name=data.name,
        description=data.description,
        tags=data.tags,
        created_by=data.created_by,
    )
    db.add(prompt)
    db.flush()

    # Create v1
    version = PromptVersionRecord(
        id=str(uuid.uuid4()),
        prompt_id=prompt.id,
        version=1,
        template=data.template,
        variables=_extract_variables(data.template),
        model=data.model,
        temperature=data.temperature,
        is_active=True,
        commit_message=data.commit_message,
        created_by=data.created_by,
    )
    db.add(version)
    db.commit()
    db.refresh(prompt)

    return _prompt_to_dict(prompt, include_versions=True)


@router.get("/{name}")
def get_prompt(
    name: str,
    project: str = Query("default"),
    db: Session = Depends(get_db),
):
    """Get a prompt with all versions."""
    prompt = (
        db.query(PromptRecord)
        .filter(PromptRecord.project == project, PromptRecord.name == name)
        .first()
    )
    if not prompt:
        raise HTTPException(404, f"Prompt '{name}' not found in project '{project}'")
    return _prompt_to_dict(prompt, include_versions=True)


@router.put("/{name}")
def update_prompt(
    name: str,
    data: PromptUpdate,
    project: str = Query("default"),
    db: Session = Depends(get_db),
):
    """Update prompt metadata (description, tags)."""
    prompt = (
        db.query(PromptRecord)
        .filter(PromptRecord.project == project, PromptRecord.name == name)
        .first()
    )
    if not prompt:
        raise HTTPException(404, "Prompt not found")

    update = data.model_dump(exclude_unset=True)
    for k, v in update.items():
        setattr(prompt, k, v)
    db.commit()
    return _prompt_to_dict(prompt, include_versions=True)


@router.delete("/{name}")
def delete_prompt(
    name: str,
    project: str = Query("default"),
    db: Session = Depends(get_db),
):
    """Delete a prompt and all its versions."""
    prompt = (
        db.query(PromptRecord)
        .filter(PromptRecord.project == project, PromptRecord.name == name)
        .first()
    )
    if not prompt:
        raise HTTPException(404, "Prompt not found")
    db.delete(prompt)
    db.commit()
    return {"status": "deleted"}


@router.post("/{name}/versions", status_code=201)
def create_version(
    name: str,
    data: VersionCreate,
    project: str = Query("default"),
    db: Session = Depends(get_db),
):
    """Create a new version of a prompt."""
    prompt = (
        db.query(PromptRecord)
        .filter(PromptRecord.project == project, PromptRecord.name == name)
        .first()
    )
    if not prompt:
        raise HTTPException(404, "Prompt not found")

    # Get next version number
    max_version = db.query(func.max(PromptVersionRecord.version)).filter(
        PromptVersionRecord.prompt_id == prompt.id
    ).scalar() or 0

    # Deactivate all existing versions
    db.query(PromptVersionRecord).filter(
        PromptVersionRecord.prompt_id == prompt.id
    ).update({"is_active": False})

    # Create new version (active by default)
    version = PromptVersionRecord(
        id=str(uuid.uuid4()),
        prompt_id=prompt.id,
        version=max_version + 1,
        template=data.template,
        variables=_extract_variables(data.template),
        model=data.model,
        temperature=data.temperature,
        is_active=True,
        commit_message=data.commit_message,
        created_by=data.created_by,
    )
    db.add(version)
    db.commit()
    db.refresh(version)

    return _version_to_dict(version)


@router.get("/{name}/versions/{version}")
def get_version(
    name: str,
    version: int,
    project: str = Query("default"),
    db: Session = Depends(get_db),
):
    """Get a specific version."""
    prompt = (
        db.query(PromptRecord)
        .filter(PromptRecord.project == project, PromptRecord.name == name)
        .first()
    )
    if not prompt:
        raise HTTPException(404, "Prompt not found")

    v = (
        db.query(PromptVersionRecord)
        .filter(PromptVersionRecord.prompt_id == prompt.id, PromptVersionRecord.version == version)
        .first()
    )
    if not v:
        raise HTTPException(404, f"Version {version} not found")
    return _version_to_dict(v)


@router.get("/{name}/latest")
def get_latest_version(
    name: str,
    project: str = Query("default"),
    db: Session = Depends(get_db),
):
    """Get the active (latest) version of a prompt."""
    prompt = (
        db.query(PromptRecord)
        .filter(PromptRecord.project == project, PromptRecord.name == name)
        .first()
    )
    if not prompt:
        raise HTTPException(404, "Prompt not found")

    active = next((v for v in prompt.versions if v.is_active), None)
    if not active:
        active = max(prompt.versions, key=lambda v: v.version) if prompt.versions else None
    if not active:
        raise HTTPException(404, "No versions found")

    return _version_to_dict(active)


@router.post("/{name}/versions/{version}/activate")
def activate_version(
    name: str,
    version: int,
    project: str = Query("default"),
    db: Session = Depends(get_db),
):
    """Mark a specific version as active (the one returned by /latest)."""
    prompt = (
        db.query(PromptRecord)
        .filter(PromptRecord.project == project, PromptRecord.name == name)
        .first()
    )
    if not prompt:
        raise HTTPException(404, "Prompt not found")

    v = (
        db.query(PromptVersionRecord)
        .filter(PromptVersionRecord.prompt_id == prompt.id, PromptVersionRecord.version == version)
        .first()
    )
    if not v:
        raise HTTPException(404, "Version not found")

    # Deactivate all
    db.query(PromptVersionRecord).filter(
        PromptVersionRecord.prompt_id == prompt.id
    ).update({"is_active": False})

    # Activate this one
    v.is_active = True
    db.commit()
    return {"status": "activated", "version": version}


@router.post("/{name}/render")
def render_prompt(
    name: str,
    variables: dict,
    version: Optional[int] = None,
    project: str = Query("default"),
    db: Session = Depends(get_db),
):
    """Render a prompt template with variables filled in."""
    prompt = (
        db.query(PromptRecord)
        .filter(PromptRecord.project == project, PromptRecord.name == name)
        .first()
    )
    if not prompt:
        raise HTTPException(404, "Prompt not found")

    if version is not None:
        v = (
            db.query(PromptVersionRecord)
            .filter(PromptVersionRecord.prompt_id == prompt.id, PromptVersionRecord.version == version)
            .first()
        )
    else:
        v = next((x for x in prompt.versions if x.is_active), None)
        if not v:
            v = max(prompt.versions, key=lambda x: x.version) if prompt.versions else None

    if not v:
        raise HTTPException(404, "Version not found")

    try:
        rendered = v.template.format(**variables)
    except KeyError as e:
        raise HTTPException(400, f"Missing variable: {e}")

    return {
        "rendered": rendered,
        "version": v.version,
        "variables_used": list(variables.keys()),
        "expected_variables": v.variables or [],
    }
