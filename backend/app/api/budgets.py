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
from app.db.models import BudgetRecord, TraceRecord, AlertChannelRecord

router = APIRouter(prefix="/budgets", tags=["budgets"])


class BudgetCreate(BaseModel):
    project: str
    name: str = "Default Budget"
    period: str = "monthly"  # daily, weekly, monthly
    amount_usd: float
    alert_thresholds: list[int] = [50, 80, 100]
    alert_channel_ids: list[str] = []  # which alert channels fire when this budget crosses thresholds


class BudgetUpdate(BaseModel):
    name: Optional[str] = None
    period: Optional[str] = None
    amount_usd: Optional[float] = None
    alert_thresholds: Optional[list[int]] = None
    alert_channel_ids: Optional[list[str]] = None
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

    # Resolve mapped channel IDs to lightweight name + type info for the UI
    channel_ids = budget.alert_channel_ids or []
    channel_summaries: list[dict] = []
    if channel_ids:
        rows = db.query(AlertChannelRecord).filter(AlertChannelRecord.id.in_(channel_ids)).all()
        existing_by_id = {r.id: r for r in rows}
        for cid in channel_ids:
            r = existing_by_id.get(cid)
            if r:
                channel_summaries.append({
                    "id": r.id,
                    "name": r.name,
                    "channel_type": r.channel_type,
                    "is_active": r.is_active,
                })

    return {
        "id": budget.id,
        "project": budget.project,
        "name": budget.name,
        "period": budget.period,
        "amount_usd": budget.amount_usd,
        "alert_thresholds": budget.alert_thresholds or [50, 80, 100],
        "alert_channel_ids": channel_ids,
        "alert_channels": channel_summaries,  # resolved for UI display
        "is_active": budget.is_active,
        "spent_usd": round(spent, 6),
        "remaining_usd": round(remaining, 6),
        "used_pct": round(used_pct, 1),
        "period_start": _get_period_start(budget.period).isoformat(),
        "status": "exceeded" if used_pct >= 100 else "warning" if used_pct >= 80 else "ok",
        "last_fired_threshold": budget.last_fired_threshold,
        "last_fired_at": budget.last_fired_at.isoformat() if budget.last_fired_at else None,
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

    # Validate channel IDs exist (silently drop unknowns rather than 400 — channels
    # may have been deleted between the user opening and submitting the form)
    valid_channel_ids: list[str] = []
    if data.alert_channel_ids:
        existing = db.query(AlertChannelRecord.id).filter(
            AlertChannelRecord.id.in_(data.alert_channel_ids)
        ).all()
        valid_channel_ids = [row[0] for row in existing]

    budget = BudgetRecord(
        id=str(uuid.uuid4()),
        project=data.project,
        name=data.name,
        period=data.period,
        amount_usd=data.amount_usd,
        alert_thresholds=data.alert_thresholds,
        alert_channel_ids=valid_channel_ids,
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

    # Validate alert_channel_ids if provided
    if "alert_channel_ids" in update and update["alert_channel_ids"] is not None:
        existing = db.query(AlertChannelRecord.id).filter(
            AlertChannelRecord.id.in_(update["alert_channel_ids"])
        ).all()
        update["alert_channel_ids"] = [row[0] for row in existing]

    for k, v in update.items():
        setattr(budget, k, v)
    db.commit()
    db.refresh(budget)
    return _budget_to_response(budget, db)


@router.post("/{budget_id}/test-fire")
def test_fire_budget(budget_id: str, db: Session = Depends(get_db)):
    """Send a synthetic alert to all channels mapped to this budget so the
    user can verify their Slack/webhook setup without waiting for a real
    threshold breach. Does NOT update last_fired_threshold."""
    budget = db.query(BudgetRecord).filter(BudgetRecord.id == budget_id).first()
    if not budget:
        raise HTTPException(404, "Budget not found")

    if not budget.alert_channel_ids:
        raise HTTPException(400, "No alert channels are mapped to this budget. Add at least one channel first.")

    # Look up the channels
    channels = db.query(AlertChannelRecord).filter(
        AlertChannelRecord.id.in_(budget.alert_channel_ids),
        AlertChannelRecord.is_active == True,
    ).all()

    if not channels:
        raise HTTPException(400, "No active alert channels found for this budget.")

    # Compute current state for a realistic-looking test message
    spent = _calculate_spent(db, budget.project, budget.period)
    used_pct = (spent / budget.amount_usd * 100) if budget.amount_usd > 0 else 0

    from app.api.alerts import _deliver_alert
    results = []
    for ch in channels:
        result = _deliver_alert(
            ch,
            event_type="budget_test",
            severity="info",
            message=(
                f"[TEST] Budget '{budget.name}' for project '{budget.project}' — "
                f"current usage: ${spent:.2f} / ${budget.amount_usd:.2f} ({used_pct:.1f}%). "
                f"This is a test message triggered manually from the dashboard."
            ),
            payload={
                "test": True,
                "budget_id": budget.id,
                "budget_name": budget.name,
                "project": budget.project,
                "period": budget.period,
                "amount_usd": budget.amount_usd,
                "spent_usd": round(spent, 4),
                "used_pct": round(used_pct, 1),
            },
            db=db,
        )
        results.append(result)

    return {
        "status": "ok",
        "budget_id": budget.id,
        "channels_fired": len(results),
        "results": results,
    }


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
