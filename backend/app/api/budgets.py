"""
Budgets API — set spending limits per project with alert thresholds.
"""

import uuid
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import Optional

from app.db.database import get_db
from app.db.models import BudgetRecord, TraceRecord

router = APIRouter(prefix="/budgets", tags=["budgets"])


class BudgetCreate(BaseModel):
    project: str
    name: str = "Default Budget"
    period: str = "monthly"  # daily, weekly, monthly
    amount_usd: float
    alert_thresholds: list[int] = [50, 80, 100]


class BudgetUpdate(BaseModel):
    name: Optional[str] = None
    period: Optional[str] = None
    amount_usd: Optional[float] = None
    alert_thresholds: Optional[list[int]] = None
    is_active: Optional[bool] = None


def _get_period_start(period: str) -> datetime:
    now = datetime.utcnow()
    if period == "daily":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "weekly":
        days_since_monday = now.weekday()
        return (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
    else:  # monthly
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _calculate_spent(db: Session, project: str, period: str) -> float:
    """Calculate total cost spent in current period for a project."""
    period_start = _get_period_start(period)
    total = (
        db.query(func.sum(TraceRecord.total_cost_usd))
        .filter(TraceRecord.project == project)
        .filter(TraceRecord.created_at >= period_start)
        .scalar()
    )
    return float(total or 0)


def _budget_to_response(budget: BudgetRecord, db: Session) -> dict:
    spent = _calculate_spent(db, budget.project, budget.period)
    used_pct = (spent / budget.amount_usd * 100) if budget.amount_usd > 0 else 0
    remaining = max(budget.amount_usd - spent, 0)

    return {
        "id": budget.id,
        "project": budget.project,
        "name": budget.name,
        "period": budget.period,
        "amount_usd": budget.amount_usd,
        "alert_thresholds": budget.alert_thresholds or [50, 80, 100],
        "is_active": budget.is_active,
        "spent_usd": round(spent, 6),
        "remaining_usd": round(remaining, 6),
        "used_pct": round(used_pct, 1),
        "period_start": _get_period_start(budget.period).isoformat(),
        "status": "exceeded" if used_pct >= 100 else "warning" if used_pct >= 80 else "ok",
        "created_at": budget.created_at.isoformat() if budget.created_at else None,
    }


@router.get("")
def list_budgets(
    project: str = Query("all"),
    db: Session = Depends(get_db),
):
    """List all budgets, optionally filtered by project."""
    query = db.query(BudgetRecord)
    if project != "all":
        query = query.filter(BudgetRecord.project == project)
    budgets = query.order_by(BudgetRecord.created_at.desc()).all()
    return {"budgets": [_budget_to_response(b, db) for b in budgets]}


@router.post("", status_code=201)
def create_budget(data: BudgetCreate, db: Session = Depends(get_db)):
    """Create a new budget."""
    if data.period not in ("daily", "weekly", "monthly"):
        raise HTTPException(400, "Period must be daily, weekly, or monthly")
    if data.amount_usd <= 0:
        raise HTTPException(400, "Amount must be > 0")

    budget = BudgetRecord(
        id=str(uuid.uuid4()),
        project=data.project,
        name=data.name,
        period=data.period,
        amount_usd=data.amount_usd,
        alert_thresholds=data.alert_thresholds,
    )
    db.add(budget)
    db.commit()
    db.refresh(budget)
    return _budget_to_response(budget, db)


@router.get("/{budget_id}")
def get_budget(budget_id: str, db: Session = Depends(get_db)):
    budget = db.query(BudgetRecord).filter(BudgetRecord.id == budget_id).first()
    if not budget:
        raise HTTPException(404, "Budget not found")
    return _budget_to_response(budget, db)


@router.put("/{budget_id}")
def update_budget(budget_id: str, data: BudgetUpdate, db: Session = Depends(get_db)):
    budget = db.query(BudgetRecord).filter(BudgetRecord.id == budget_id).first()
    if not budget:
        raise HTTPException(404, "Budget not found")

    update = data.model_dump(exclude_unset=True)
    for k, v in update.items():
        setattr(budget, k, v)
    db.commit()
    db.refresh(budget)
    return _budget_to_response(budget, db)


@router.delete("/{budget_id}")
def delete_budget(budget_id: str, db: Session = Depends(get_db)):
    budget = db.query(BudgetRecord).filter(BudgetRecord.id == budget_id).first()
    if not budget:
        raise HTTPException(404, "Budget not found")
    db.delete(budget)
    db.commit()
    return {"status": "deleted"}


@router.get("/project/{project}/status")
def get_project_budget_status(project: str, db: Session = Depends(get_db)):
    """Quick status check for a project's active budget."""
    budgets = db.query(BudgetRecord).filter(
        BudgetRecord.project == project,
        BudgetRecord.is_active == True,
    ).all()
    return {
        "project": project,
        "budgets": [_budget_to_response(b, db) for b in budgets],
    }
