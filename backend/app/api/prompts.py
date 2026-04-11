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
    project: str = "global"  # legacy — kept for backward compat, but prompts are now global


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

# Variable placeholder regex — matches {{identifier}} only.
# Single { and } are always literal characters in this template syntax.
_VAR_PATTERN = re.compile(r"\{\{(\w+)\}\}")

# Catch the legacy single-brace style so we can warn users that it's no longer supported
_LEGACY_VAR_PATTERN = re.compile(r"(?<!\{)\{(\w+)\}(?!\})")


def _extract_variables(template: str) -> list[str]:
    """Extract {{variable}} names from a template string. Single-brace
    syntax is no longer supported as of v0.6.4 — use double braces."""
    return list(set(_VAR_PATTERN.findall(template)))


def _render_template_string(template: str, kwargs: dict) -> tuple[str, list[str]]:
    """Substitute {{varname}} placeholders. Returns (rendered, missing_vars)."""
    missing: list[str] = []

    def replace(match: re.Match) -> str:
        var = match.group(1)
        if var in kwargs:
            return str(kwargs[var])
        missing.append(var)
        return match.group(0)

    rendered = _VAR_PATTERN.sub(replace, template)
    return rendered, missing


def _validate_template(template: str) -> dict:
    """
    Validate a prompt template using the v0.6.4+ {{varname}} syntax.

    Returns a dict with:
      - is_valid (bool)
      - variables (list of declared variable names)
      - warnings (list of human-readable strings, NOT fatal)
      - errors   (list of human-readable strings, fatal — render will fail)

    The frontend uses this to show inline feedback at save time and the
    backend uses it to refuse outright-broken templates.
    """
    warnings: list[str] = []
    errors: list[str] = []
    variables = _extract_variables(template)

    # Attempt a real render with placeholder values for every declared variable
    fake_kwargs = {v: f"<{v}>" for v in variables}
    rendered, missing = _render_template_string(template, fake_kwargs)
    if missing:
        # This shouldn't happen since we passed kwargs for everything in `variables`
        # but defensive in case the regex behaves unexpectedly
        unique = sorted(set(missing))
        errors.append(
            f"Template references unknown variables: {unique}. "
            f"Make sure each {{{{varname}}}} matches the variables you'll pass at render time."
        )

    # Soft warnings — things that aren't broken but look suspicious

    # 1. Legacy single-brace syntax {var} — would have worked in v0.6.3 but not now
    legacy_matches = _LEGACY_VAR_PATTERN.findall(template)
    if legacy_matches:
        unique_legacy = sorted(set(legacy_matches))
        warnings.append(
            f"Found single-brace placeholders that look like the old syntax: "
            f"{', '.join('{' + v + '}' for v in unique_legacy)}. "
            f"In v0.6.4+ these are treated as literal text — use {{{{varname}}}} "
            f"(double braces) instead. If these are meant to be literal characters, ignore this warning."
        )

    # 2. Empty {{}} or {{ }} placeholders
    if re.search(r"\{\{\s*\}\}", template):
        warnings.append(
            "Template contains empty `{{}}` placeholders. These will not be substituted "
            "and will appear as literal `{{}}` in the rendered output."
        )

    return {
        "is_valid": len(errors) == 0,
        "variables": sorted(variables),
        "warnings": warnings,
        "errors": errors,
    }


def _find_prompt(db: Session, name: str) -> Optional[PromptRecord]:
    """Find a prompt by name. Prompts are now global — project filter is ignored.
    Returns the most recently updated prompt with this name (handles legacy duplicates)."""
    return (
        db.query(PromptRecord)
        .filter(PromptRecord.name == name)
        .order_by(PromptRecord.updated_at.desc())
        .first()
    )


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
        "metadata": v.metadata_json or {},
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
    project: str = Query("all"),  # kept for backward compat — ignored, prompts are now global
    tag: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List all prompts. Prompts are now globally accessible — the project
    query parameter is accepted for backward compatibility but ignored."""
    prompts = db.query(PromptRecord).order_by(PromptRecord.updated_at.desc()).all()

    result = [_prompt_to_dict(p) for p in prompts]
    if tag:
        result = [p for p in result if tag in (p.get("tags") or [])]
    return {"prompts": result}


@router.post("/validate")
def validate_template_endpoint(payload: dict):
    """Standalone validation endpoint — used by the frontend to give live
    feedback in the prompt create/edit form before the user clicks Save.
    Accepts {"template": "..."} and returns {is_valid, variables, warnings, errors}."""
    template = payload.get("template", "")
    return _validate_template(template)


@router.post("", status_code=201)
def create_prompt(data: PromptCreate, db: Session = Depends(get_db)):
    """Create a new prompt with its first version. Names must be globally unique."""
    existing = _find_prompt(db, data.name)
    if existing:
        raise HTTPException(409, f"Prompt '{data.name}' already exists")

    # Validate the template before saving so users get a clear error
    # at save time, not at first render time
    validation = _validate_template(data.template)
    if not validation["is_valid"]:
        raise HTTPException(400, {
            "message": "Template has rendering errors",
            "errors": validation["errors"],
            "warnings": validation["warnings"],
            "variables": validation["variables"],
        })

    prompt = PromptRecord(
        id=str(uuid.uuid4()),
        project="global",
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

    response = _prompt_to_dict(prompt, include_versions=True)
    # Include any soft warnings so the UI can display them after save
    if validation["warnings"]:
        response["validation_warnings"] = validation["warnings"]
    return response


@router.get("/{name}")
def get_prompt(
    name: str,
    project: str = Query("default"),  # accepted but ignored
    db: Session = Depends(get_db),
):
    """Get a prompt with all versions. Prompts are global — name is sufficient."""
    prompt = _find_prompt(db, name)
    if not prompt:
        raise HTTPException(404, f"Prompt '{name}' not found")
    return _prompt_to_dict(prompt, include_versions=True)


@router.put("/{name}")
def update_prompt(
    name: str,
    data: PromptUpdate,
    project: str = Query("default"),  # accepted but ignored
    db: Session = Depends(get_db),
):
    """Update prompt metadata (description, tags)."""
    prompt = _find_prompt(db, name)
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
    project: str = Query("default"),  # accepted but ignored
    db: Session = Depends(get_db),
):
    """Delete a prompt and all its versions."""
    prompt = _find_prompt(db, name)
    if not prompt:
        raise HTTPException(404, "Prompt not found")
    db.delete(prompt)
    db.commit()
    return {"status": "deleted"}


@router.post("/{name}/versions", status_code=201)
def create_version(
    name: str,
    data: VersionCreate,
    project: str = Query("default"),  # accepted but ignored
    db: Session = Depends(get_db),
):
    """Create a new version of a prompt."""
    prompt = _find_prompt(db, name)
    if not prompt:
        raise HTTPException(404, "Prompt not found")

    # Validate the template before saving
    validation = _validate_template(data.template)
    if not validation["is_valid"]:
        raise HTTPException(400, {
            "message": "Template has rendering errors",
            "errors": validation["errors"],
            "warnings": validation["warnings"],
            "variables": validation["variables"],
        })

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

    response = _version_to_dict(version)
    if validation["warnings"]:
        response["validation_warnings"] = validation["warnings"]
    return response


@router.get("/{name}/versions/{version}")
def get_version(
    name: str,
    version: int,
    project: str = Query("default"),  # accepted but ignored
    db: Session = Depends(get_db),
):
    """Get a specific version."""
    prompt = _find_prompt(db, name)
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
    project: str = Query("default"),  # accepted but ignored
    db: Session = Depends(get_db),
):
    """Get the active (latest) version of a prompt."""
    prompt = _find_prompt(db, name)
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
    project: str = Query("default"),  # accepted but ignored
    db: Session = Depends(get_db),
):
    """Mark a specific version as active (the one returned by /latest)."""
    prompt = _find_prompt(db, name)
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
    project: str = Query("default"),  # accepted but ignored
    db: Session = Depends(get_db),
):
    """Render a prompt template with variables filled in."""
    prompt = _find_prompt(db, name)
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

    rendered, missing = _render_template_string(v.template, variables)
    if missing:
        unique = sorted(set(missing))
        raise HTTPException(400, f"Missing variable(s) at render time: {unique}")

    return {
        "rendered": rendered,
        "version": v.version,
        "variables_used": list(variables.keys()),
        "expected_variables": v.variables or [],
    }


# ========================================
# MERGE — combine multiple versions using LLM
# ========================================

# Static system prompt for merging — controlled by us, not user.
# Instructs the merge LLM to use the v0.6.4+ double-brace placeholder syntax.
MERGE_SYSTEM_PROMPT = """You are a prompt engineering expert. You are given multiple versions of a prompt template.

Your task is to analyze each version, identify the strengths of each, and create a single merged version that combines the best aspects of all of them.

CRITICAL TEMPLATE SYNTAX RULES:
- Variable placeholders use DOUBLE curly braces: __DOUBLE_OPEN__varname__DOUBLE_CLOSE__
- Single curly braces __SINGLE_OPEN__ and __SINGLE_CLOSE__ are LITERAL characters and are passed through as-is. Do NOT escape them.
- This means JSON examples in prompts work without any escaping. You can write something like: Return JSON in this format: __SINGLE_OPEN__"key": "value"__SINGLE_CLOSE__
- The variables that must be present in the output (using double-brace syntax) are: __EXPECTED_VARS__

Other rules:
1. The merged version MUST keep the SAME variable names as the originals. Do not invent new variables, do not remove existing ones.
2. Preserve the double-brace syntax exactly. If an original version uses __DOUBLE_OPEN__question__DOUBLE_CLOSE__, your output must also use __DOUBLE_OPEN__question__DOUBLE_CLOSE__.
3. Keep the merged version concise but complete.
4. Preserve any explicit instructions, constraints, or rules from any version.
5. If versions conflict, prefer the more specific/strict instruction.
6. Return ONLY the merged template text. No explanation, no markdown code fences, no commentary.

Versions to merge:
__VERSIONS_TEXT__
__EXTRA_INSTRUCTIONS_BLOCK__
Now return only the merged template (and nothing else):"""


# In-memory draft storage
_drafts: dict[str, dict] = {}


class MergeRequest(BaseModel):
    versions: list[int]                    # e.g. [2, 3]
    llm_config_id: Optional[str] = None    # which LLM to use; if None, picks auto-eval LLM
    extra_instructions: Optional[str] = None  # optional edge cases / extra guidance from the user


@router.post("/{name}/merge")
def merge_versions(
    name: str,
    req: MergeRequest,
    project: str = Query("default"),  # accepted but ignored
    db: Session = Depends(get_db),
):
    """
    Merge multiple versions of a prompt using an LLM.
    Returns a draft (not yet saved as a version).
    """
    if len(req.versions) < 2:
        raise HTTPException(400, "Need at least 2 versions to merge")

    prompt_record = _find_prompt(db, name)
    if not prompt_record:
        raise HTTPException(404, "Prompt not found")

    # Fetch the requested versions
    selected = []
    for vnum in req.versions:
        v = next((x for x in prompt_record.versions if x.version == vnum), None)
        if not v:
            raise HTTPException(404, f"Version {vnum} not found")
        selected.append(v)

    # Collect expected variables (union)
    all_vars = set()
    for v in selected:
        all_vars.update(v.variables or [])
    expected_vars = sorted(all_vars)

    # Build versions text
    versions_text = "\n\n".join([
        f"--- Version {v.version} ---\n{v.template}"
        for v in selected
    ])

    # Get LLM to use
    from app.db.models import LLMConfigRecord
    llm_cfg = None
    if req.llm_config_id:
        llm_cfg = db.query(LLMConfigRecord).filter(LLMConfigRecord.id == req.llm_config_id).first()
    if not llm_cfg:
        # Default to auto-eval LLM
        llm_cfg = (
            db.query(LLMConfigRecord)
            .filter(LLMConfigRecord.use_for_auto_eval == True, LLMConfigRecord.is_active == True)
            .first()
        )
    if not llm_cfg:
        # Fallback to any active LLM
        llm_cfg = db.query(LLMConfigRecord).filter(LLMConfigRecord.is_active == True).first()
    if not llm_cfg:
        raise HTTPException(400, "No LLM configured. Add an LLM in LLM Config first.")

    # Build the merge prompt. We use string replace (not .format) so that
    # literal { and } characters in the rules text and versions_text don't
    # conflict with Python's format syntax.
    # Variables in the OUTPUT use double-brace syntax — show them in the
    # rules so the LLM matches the convention.
    expected_vars_str = ", ".join(f"{{{{{v}}}}}" for v in expected_vars)

    # Optional user-provided edge cases / extra guidance
    extra_block = ""
    if req.extra_instructions and req.extra_instructions.strip():
        extra_block = (
            "\n\nADDITIONAL USER GUIDANCE — must be followed in addition to the rules above:\n"
            f"{req.extra_instructions.strip()}\n"
        )

    merge_prompt = (
        MERGE_SYSTEM_PROMPT
        # First substitute the brace placeholders so the rules text reads naturally
        .replace("__DOUBLE_OPEN__", "{{")
        .replace("__DOUBLE_CLOSE__", "}}")
        .replace("__SINGLE_OPEN__", "{")
        .replace("__SINGLE_CLOSE__", "}")
        # Then substitute the dynamic content
        .replace("__EXPECTED_VARS__", expected_vars_str)
        .replace("__VERSIONS_TEXT__", versions_text)
        .replace("__EXTRA_INSTRUCTIONS_BLOCK__", extra_block)
    )

    # Call the LLM via LiteLLM
    try:
        from litellm import completion
        prefixes = {
            "openai": "", "azure_openai": "azure/", "anthropic": "anthropic/",
            "gemini": "gemini/", "ollama": "ollama/", "groq": "groq/",
        }
        prefix = prefixes.get(llm_cfg.provider, "")
        if llm_cfg.provider == "azure_openai" and llm_cfg.azure_deployment:
            model = f"azure/{llm_cfg.azure_deployment}"
        else:
            model = f"{prefix}{llm_cfg.model_id}"

        kwargs = {
            "model": model,
            "messages": [{"role": "user", "content": merge_prompt}],
            "temperature": 0.2,
        }
        if llm_cfg.provider == "azure_openai":
            kwargs["max_completion_tokens"] = 1024
            kwargs["api_version"] = llm_cfg.api_version
        else:
            kwargs["max_tokens"] = 1024
        if llm_cfg.api_key:
            kwargs["api_key"] = llm_cfg.api_key
        if llm_cfg.api_base:
            kwargs["api_base"] = llm_cfg.api_base

        response = completion(**kwargs)
        merged_template = response.choices[0].message.content.strip()

        # Strip code fences if LLM included them
        if merged_template.startswith("```"):
            lines = merged_template.split("\n")
            merged_template = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

    except Exception as e:
        raise HTTPException(500, f"LLM merge failed: {str(e)}")

    # Validate variables
    actual_vars = set(_extract_variables(merged_template))
    missing = set(expected_vars) - actual_vars
    extra = actual_vars - set(expected_vars)

    # Create draft
    draft_id = str(uuid.uuid4())
    _drafts[draft_id] = {
        "draft_id": draft_id,
        "prompt_name": name,
        "project": project,
        "merged_from": req.versions,
        "merged_by_llm": f"{llm_cfg.provider}/{llm_cfg.model_id}",
        "llm_config_id": llm_cfg.id,
        "merged_template": merged_template,
        "expected_variables": expected_vars,
        "actual_variables": sorted(actual_vars),
        "missing_variables": sorted(missing),
        "extra_variables": sorted(extra),
        "extra_instructions": req.extra_instructions or "",
        "warnings": [],
    }

    if missing:
        _drafts[draft_id]["warnings"].append(f"Missing variables: {sorted(missing)}")
    if extra:
        _drafts[draft_id]["warnings"].append(f"Extra variables (not in originals): {sorted(extra)}")

    return _drafts[draft_id]


@router.get("/drafts/{draft_id}")
def get_draft(draft_id: str):
    """Get a merge draft by ID."""
    draft = _drafts.get(draft_id)
    if not draft:
        raise HTTPException(404, "Draft not found or expired")
    return draft


class ApproveDraftRequest(BaseModel):
    template: Optional[str] = None  # User can edit the merged template before approving
    commit_message: Optional[str] = None


@router.post("/drafts/{draft_id}/approve")
def approve_draft(
    draft_id: str,
    req: ApproveDraftRequest,
    db: Session = Depends(get_db),
):
    """Approve a draft and create a new version of the prompt."""
    draft = _drafts.get(draft_id)
    if not draft:
        raise HTTPException(404, "Draft not found or expired")

    prompt_record = _find_prompt(db, draft["prompt_name"])
    if not prompt_record:
        raise HTTPException(404, "Prompt not found")

    # Get next version
    max_version = db.query(func.max(PromptVersionRecord.version)).filter(
        PromptVersionRecord.prompt_id == prompt_record.id
    ).scalar() or 0

    # Deactivate all
    db.query(PromptVersionRecord).filter(
        PromptVersionRecord.prompt_id == prompt_record.id
    ).update({"is_active": False})

    # Use edited template if provided
    final_template = req.template or draft["merged_template"]

    # Create new version
    version = PromptVersionRecord(
        id=str(uuid.uuid4()),
        prompt_id=prompt_record.id,
        version=max_version + 1,
        template=final_template,
        variables=_extract_variables(final_template),
        is_active=True,
        commit_message=req.commit_message or f"Merged from versions {draft['merged_from']} using {draft['merged_by_llm']}",
        created_by="merge-ai",
        metadata_json={
            "merged_from": draft["merged_from"],
            "merged_by_llm": draft["merged_by_llm"],
        },
    )
    db.add(version)
    db.commit()
    db.refresh(version)

    # Remove draft
    _drafts.pop(draft_id, None)

    return _version_to_dict(version)


@router.delete("/drafts/{draft_id}")
def discard_draft(draft_id: str):
    """Discard a draft."""
    if draft_id in _drafts:
        del _drafts[draft_id]
    return {"status": "discarded"}
