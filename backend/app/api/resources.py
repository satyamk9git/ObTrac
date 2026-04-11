"""
Resources API - Ground truth upload and management.
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
from typing import Optional
import uuid
import json
import csv
import io

from app.db.database import get_db
from app.db.models import GroundTruthRecord

router = APIRouter(prefix="/resources", tags=["resources"])


@router.post("/ground-truth/upload")
async def upload_ground_truth(
    file: UploadFile = File(...),
    project: str = Form("default"),
    dataset_name: str = Form(""),
    db: Session = Depends(get_db),
):
    """
    Upload ground truth data as CSV or JSON.

    CSV format: question, ground_truth, context (optional)
    JSON format: [{"question": "...", "ground_truth": "...", "context": "..."}]
    """
    content = await file.read()
    content_str = content.decode("utf-8")

    records = []

    if file.filename.endswith(".csv"):
        reader = csv.DictReader(io.StringIO(content_str))
        for row in reader:
            if "question" not in row or "ground_truth" not in row:
                raise HTTPException(
                    status_code=400,
                    detail="CSV must have 'question' and 'ground_truth' columns",
                )
            records.append(
                {
                    "question": row["question"],
                    "ground_truth": row["ground_truth"],
                    "context": row.get("context", ""),
                }
            )
    elif file.filename.endswith(".json"):
        try:
            data = json.loads(content_str)
            if isinstance(data, list):
                records = data
            else:
                raise HTTPException(status_code=400, detail="JSON must be a list of objects")
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON file")
    else:
        raise HTTPException(status_code=400, detail="Only CSV and JSON files supported")

    # Store records
    created = 0
    for record in records:
        gt = GroundTruthRecord(
            id=str(uuid.uuid4()),
            project=project,
            dataset_name=dataset_name or file.filename,
            question=record.get("question", ""),
            ground_truth=record.get("ground_truth", ""),
            context=record.get("context", ""),
            metadata_json=record.get("metadata", {}),
        )
        db.add(gt)
        created += 1

    db.commit()

    return {
        "status": "uploaded",
        "filename": file.filename,
        "records_created": created,
        "dataset_name": dataset_name or file.filename,
        "project": project,
    }


@router.get("/ground-truth")
def list_ground_truths(
    project: str = Query("default"),
    dataset_name: Optional[str] = None,
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List ground truth records."""
    query = db.query(GroundTruthRecord).filter(GroundTruthRecord.project == project)

    if dataset_name:
        query = query.filter(GroundTruthRecord.dataset_name == dataset_name)

    total = query.count()
    records = query.offset(offset).limit(limit).all()

    return {
        "total": total,
        "records": [
            {
                "id": r.id,
                "question": r.question,
                "ground_truth": r.ground_truth,
                "context": r.context,
                "dataset_name": r.dataset_name,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ],
    }


@router.get("/ground-truth/datasets")
def list_datasets(
    project: str = Query("default"),
    db: Session = Depends(get_db),
):
    """List all ground truth dataset names."""
    from sqlalchemy import distinct, func

    datasets = (
        db.query(
            GroundTruthRecord.dataset_name,
            func.count(GroundTruthRecord.id).label("count"),
        )
        .filter(GroundTruthRecord.project == project)
        .group_by(GroundTruthRecord.dataset_name)
        .all()
    )

    return {
        "datasets": [
            {"name": d.dataset_name, "count": d.count} for d in datasets
        ]
    }


@router.get("/ground-truth/match")
def match_ground_truth(
    question: str = Query(...),
    project: str = Query("default"),
    db: Session = Depends(get_db),
):
    """Find the closest ground truth match for a question (exact match)."""
    record = (
        db.query(GroundTruthRecord)
        .filter(GroundTruthRecord.project == project)
        .filter(GroundTruthRecord.question == question)
        .first()
    )

    if not record:
        return {"found": False, "ground_truth": None}

    return {
        "found": True,
        "ground_truth": record.ground_truth,
        "context": record.context,
        "dataset_name": record.dataset_name,
    }


@router.delete("/ground-truth/{record_id}")
def delete_ground_truth(record_id: str, db: Session = Depends(get_db)):
    record = db.query(GroundTruthRecord).filter(GroundTruthRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    db.delete(record)
    db.commit()
    return {"status": "deleted"}


# Cache for dataset embeddings — keyed by (project, dataset, embedder_id) so
# that switching the default embedder doesn't return stale vectors.
_dataset_embeddings_cache: dict = {}


@router.get("/ground-truth/match")
def match_ground_truth_semantic(
    query: str = Query(..., description="The query to match against dataset questions"),
    dataset_name: str = Query(..., description="Name of the dataset to search"),
    project: str = Query("default"),
    db: Session = Depends(get_db),
):
    """
    Find the closest ground truth record in a dataset using semantic similarity.
    Returns the best match with similarity score.
    """
    # Fetch all records in the dataset
    records = (
        db.query(GroundTruthRecord)
        .filter(GroundTruthRecord.project == project)
        .filter(GroundTruthRecord.dataset_name == dataset_name)
        .all()
    )

    if not records:
        return {"found": False, "match": None, "score": 0}

    # Try exact match first (fastest)
    for r in records:
        if r.question.strip().lower() == query.strip().lower():
            return {
                "found": True,
                "match": {
                    "id": r.id,
                    "question": r.question,
                    "ground_truth": r.ground_truth,
                    "context": r.context,
                },
                "score": 1.0,
                "match_type": "exact",
            }

    # Semantic match using embeddings — uses the default Embedder Config
    # (Embedder Config page) if set, otherwise falls back to local MiniLM.
    try:
        import numpy as np
        from app.db.models import EmbedderConfigRecord
        from app.services.embedder import get_embeddings

        active_embedder = (
            db.query(EmbedderConfigRecord)
            .filter(EmbedderConfigRecord.is_default == True, EmbedderConfigRecord.is_active == True)
            .first()
        )
        embedder_id = active_embedder.id if active_embedder else "fallback-minilm"

        cache_key = f"{project}:{dataset_name}:{embedder_id}"
        cached = _dataset_embeddings_cache.get(cache_key)

        # Cache invalidation: re-embed if record count changed
        if not cached or len(cached.get("records", [])) != len(records):
            questions = [r.question for r in records]
            embeddings = np.array(
                get_embeddings(questions, db=db, embedder=active_embedder),
                dtype=np.float32,
            )
            cached = {"records": records, "embeddings": embeddings}
            _dataset_embeddings_cache[cache_key] = cached

        # Embed the query using the same embedder
        query_emb = np.array(
            get_embeddings([query], db=db, embedder=active_embedder)[0],
            dtype=np.float32,
        )

        # Cosine similarity
        embeddings = cached["embeddings"]
        norms = np.linalg.norm(embeddings, axis=1) * np.linalg.norm(query_emb)
        norms[norms == 0] = 1e-10
        similarities = (embeddings @ query_emb) / norms

        best_idx = int(np.argmax(similarities))
        best_score = float(similarities[best_idx])
        best_record = cached["records"][best_idx]

        return {
            "found": True,
            "match": {
                "id": best_record.id,
                "question": best_record.question,
                "ground_truth": best_record.ground_truth,
                "context": best_record.context,
            },
            "score": round(best_score, 4),
            "match_type": "semantic",
        }
    except Exception as e:
        return {"found": False, "match": None, "score": 0, "error": str(e)}


@router.delete("/ground-truth/dataset/{dataset_name}")
def delete_dataset(
    dataset_name: str,
    project: str = Query("default"),
    db: Session = Depends(get_db),
):
    """Delete all records in a dataset."""
    deleted = (
        db.query(GroundTruthRecord)
        .filter(GroundTruthRecord.project == project)
        .filter(GroundTruthRecord.dataset_name == dataset_name)
        .delete()
    )
    db.commit()
    return {"status": "deleted", "records_deleted": deleted}


# ========================================
# AI Ground Truth Generator
# ========================================

# Static system prompt for golden dataset generation
GOLDEN_DATASET_PROMPT = """You are an expert at creating high-quality test datasets for RAG (Retrieval-Augmented Generation) systems.

Your task: Read the document below and generate exactly __NUM_QUESTIONS__ diverse question-answer pairs that test understanding of the content.

Rules:
1. Generate a MIX of question types:
   - Factual (who, what, when, where)
   - Analytical (why, how, compare)
   - Inferential (what can we conclude)
   - Specific detail (numbers, dates, names)
2. Each question must be answerable using ONLY the document.
3. Each ground_truth answer must be FACTUAL and grounded in the document text.
4. Include a "context" field that quotes the EXACT relevant passage from the document.
5. Vary question difficulty from easy to hard.
6. Do NOT make up information not in the document.
7. Return ONLY a valid JSON array. No markdown, no explanation, no commentary.

Output format (strict JSON):
[
  {"question": "...", "ground_truth": "...", "context": "exact quote from document"},
  ...
]

Document to analyze:
__DOCUMENT__

Generate exactly __NUM_QUESTIONS__ Q&A pairs as a JSON array. Output ONLY the JSON array."""


@router.post("/ground-truth/generate")
async def generate_ground_truth(
    file: UploadFile = File(...),
    project: str = Form("default"),
    dataset_name: str = Form(""),
    num_questions: int = Form(10),
    llm_config_id: str = Form(""),
    save: bool = Form(False),
    db: Session = Depends(get_db),
):
    """
    Generate a golden ground truth dataset from an uploaded document using an LLM.
    """
    if num_questions < 1 or num_questions > 1000:
        raise HTTPException(400, "num_questions must be between 1 and 1000")

    # Read file content
    import tempfile
    import os as _os
    suffix = _os.path.splitext(file.filename)[1]
    content = await file.read()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        if suffix.lower() == ".pdf":
            from langchain_community.document_loaders import PyPDFLoader
            loader = PyPDFLoader(tmp_path)
            docs = loader.load()
            doc_text = "\n\n".join([d.page_content for d in docs])
        else:
            doc_text = content.decode("utf-8", errors="ignore")
    finally:
        _os.unlink(tmp_path)

    if not doc_text.strip():
        raise HTTPException(400, "Document is empty")

    # Truncate very long documents to fit context window (~30K chars)
    if len(doc_text) > 30000:
        doc_text = doc_text[:30000] + "\n\n... [truncated]"

    # Get LLM
    from app.db.models import LLMConfigRecord
    llm_cfg = None
    if llm_config_id:
        llm_cfg = db.query(LLMConfigRecord).filter(LLMConfigRecord.id == llm_config_id).first()
    if not llm_cfg:
        llm_cfg = (
            db.query(LLMConfigRecord)
            .filter(LLMConfigRecord.use_for_auto_eval == True, LLMConfigRecord.is_active == True)
            .first()
        )
    if not llm_cfg:
        llm_cfg = db.query(LLMConfigRecord).filter(LLMConfigRecord.is_active == True).first()
    if not llm_cfg:
        raise HTTPException(400, "No LLM configured. Add an LLM in LLM Config first.")

    # Build prompt
    prompt = (
        GOLDEN_DATASET_PROMPT
        .replace("__NUM_QUESTIONS__", str(num_questions))
        .replace("__DOCUMENT__", doc_text)
    )

    # Call LLM
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

        # Allow large output for many questions
        max_tok = max(2048, num_questions * 150)

        kwargs = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.4,
        }
        if llm_cfg.provider == "azure_openai":
            kwargs["max_completion_tokens"] = max_tok
            kwargs["api_version"] = llm_cfg.api_version
        else:
            kwargs["max_tokens"] = max_tok
        if llm_cfg.api_key:
            kwargs["api_key"] = llm_cfg.api_key
        if llm_cfg.api_base:
            kwargs["api_base"] = llm_cfg.api_base

        response = completion(**kwargs)
        raw_output = response.choices[0].message.content.strip()

        # Strip markdown code fences if present
        if raw_output.startswith("```"):
            lines = raw_output.split("\n")
            raw_output = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

        # Parse JSON
        try:
            generated = json.loads(raw_output)
            if not isinstance(generated, list):
                raise ValueError("Output is not a JSON array")
        except json.JSONDecodeError as e:
            # Try to extract JSON array from the text
            import re as _re
            match = _re.search(r"\[.*\]", raw_output, _re.DOTALL)
            if match:
                generated = json.loads(match.group(0))
            else:
                raise HTTPException(500, f"LLM returned invalid JSON: {str(e)[:200]}")

        # Validate records
        valid_records = []
        for r in generated:
            if isinstance(r, dict) and "question" in r and "ground_truth" in r:
                valid_records.append({
                    "question": str(r.get("question", "")),
                    "ground_truth": str(r.get("ground_truth", "")),
                    "context": str(r.get("context", "")),
                })

        if not valid_records:
            raise HTTPException(500, "LLM did not return any valid Q&A records")

        # Optionally save to DB
        saved_count = 0
        if save:
            ds_name = dataset_name or f"ai-generated-{file.filename}"
            for r in valid_records:
                gt = GroundTruthRecord(
                    id=str(uuid.uuid4()),
                    project=project,
                    dataset_name=ds_name,
                    question=r["question"],
                    ground_truth=r["ground_truth"],
                    context=r["context"],
                    metadata_json={"generated_by": "ai", "source_file": file.filename, "llm": f"{llm_cfg.provider}/{llm_cfg.model_id}"},
                )
                db.add(gt)
                saved_count += 1
            db.commit()

        return {
            "status": "generated",
            "filename": file.filename,
            "num_generated": len(valid_records),
            "num_requested": num_questions,
            "records": valid_records,
            "llm_used": f"{llm_cfg.provider}/{llm_cfg.model_id}",
            "saved_to_db": saved_count,
            "dataset_name": dataset_name or (f"ai-generated-{file.filename}" if save else None),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Generation failed: {str(e)[:300]}")
