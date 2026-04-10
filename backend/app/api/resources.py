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
