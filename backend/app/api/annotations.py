"""
Annotations API — Rate and label traces with human feedback.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import Optional
import uuid

from app.db.database import get_db
from app.db.models import AnnotationRecord, TraceRecord

router = APIRouter(prefix="/annotations", tags=["annotations"])


class AnnotationCreate(BaseModel):
    trace_id: str
    rating: str = ""  # thumbs_up, thumbs_down, neutral
    label: str = ""  # correct, incorrect, partial, hallucination, irrelevant
    notes: str = ""
    annotated_by: str = ""


class AnnotationUpdate(BaseModel):
    rating: Optional[str] = None
    label: Optional[str] = None
    notes: Optional[str] = None


@router.post("", status_code=201)
def create_annotation(data: AnnotationCreate, db: Session = Depends(get_db)):
    """Add an annotation to a trace."""
    trace = db.query(TraceRecord).filter(TraceRecord.trace_id == data.trace_id).first()
    if not trace:
        raise HTTPException(404, "Trace not found")

    annotation = AnnotationRecord(
        id=str(uuid.uuid4()),
        trace_id=data.trace_id,
        rating=data.rating,
        label=data.label,
        notes=data.notes,
        annotated_by=data.annotated_by,
    )
    db.add(annotation)
    db.commit()
    db.refresh(annotation)
    return {
        "id": annotation.id,
        "trace_id": annotation.trace_id,
        "rating": annotation.rating,
        "label": annotation.label,
        "notes": annotation.notes,
        "annotated_by": annotation.annotated_by,
        "created_at": annotation.created_at.isoformat() if annotation.created_at else None,
    }


@router.get("/trace/{trace_id}")
def get_trace_annotations(trace_id: str, db: Session = Depends(get_db)):
    """Get all annotations for a trace."""
    annotations = (
        db.query(AnnotationRecord)
        .filter(AnnotationRecord.trace_id == trace_id)
        .order_by(AnnotationRecord.created_at.desc())
        .all()
    )
    return {
        "trace_id": trace_id,
        "annotations": [
            {
                "id": a.id,
                "rating": a.rating,
                "label": a.label,
                "notes": a.notes,
                "annotated_by": a.annotated_by,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in annotations
        ],
    }


@router.put("/{annotation_id}")
def update_annotation(annotation_id: str, data: AnnotationUpdate, db: Session = Depends(get_db)):
    """Update an annotation."""
    annotation = db.query(AnnotationRecord).filter(AnnotationRecord.id == annotation_id).first()
    if not annotation:
        raise HTTPException(404, "Annotation not found")

    update = data.model_dump(exclude_unset=True)
    for k, v in update.items():
        setattr(annotation, k, v)
    db.commit()
    return {"status": "updated", "id": annotation_id}


@router.delete("/{annotation_id}")
def delete_annotation(annotation_id: str, db: Session = Depends(get_db)):
    annotation = db.query(AnnotationRecord).filter(AnnotationRecord.id == annotation_id).first()
    if not annotation:
        raise HTTPException(404, "Annotation not found")
    db.delete(annotation)
    db.commit()
    return {"status": "deleted"}


@router.get("/summary")
def get_annotation_summary(
    project: str = Query("all"),
    db: Session = Depends(get_db),
):
    """Summary stats of annotations."""
    query = db.query(AnnotationRecord)
    if project != "all":
        query = query.join(TraceRecord).filter(TraceRecord.project == project)

    total = query.count()

    ratings = {}
    for rating, count in query.with_entities(AnnotationRecord.rating, func.count()).group_by(AnnotationRecord.rating).all():
        ratings[rating or "none"] = count

    labels = {}
    for label, count in query.with_entities(AnnotationRecord.label, func.count()).group_by(AnnotationRecord.label).all():
        labels[label or "none"] = count

    return {
        "total_annotations": total,
        "by_rating": ratings,
        "by_label": labels,
    }
