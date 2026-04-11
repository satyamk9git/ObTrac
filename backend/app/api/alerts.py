"""
Alerts API — webhook/slack channels and delivery.
"""

import uuid
import json
import logging
import requests
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.db.database import get_db
from app.db.models import AlertChannelRecord, AlertHistoryRecord, BudgetRecord, TraceRecord
from app.api.budgets import _calculate_spent

logger = logging.getLogger("obtrac")

router = APIRouter(prefix="/alerts", tags=["alerts"])


# Available trigger event types — for non-budget events.
# Budget alerts (50/80/100) are now wired per-budget via the explicit
# `BudgetRecord.alert_channel_ids` mapping, so they don't appear here anymore.
# The `budget_*` event types are still RECEIVED by the delivery code path
# (legacy fallback when a budget has no explicit channel mapping), they're
# just no longer shown as trigger options on the channel form.
TRIGGER_TYPES = {
    "metric_low": "Metric drops below threshold",
    "error_spike": "Error rate spike",
    "trace_failed": "Any trace failed",
}


class ChannelCreate(BaseModel):
    name: str
    channel_type: str = "webhook"  # webhook, slack
    config: dict  # {"url": "https://hooks.slack.com/...", "headers": {}}
    project: str = "all"
    triggers: list[str] = []


class ChannelUpdate(BaseModel):
    name: Optional[str] = None
    channel_type: Optional[str] = None
    config: Optional[dict] = None
    project: Optional[str] = None
    triggers: Optional[list[str]] = None
    is_active: Optional[bool] = None


class TestChannelRequest(BaseModel):
    config: dict
    channel_type: str = "webhook"


def _channel_to_dict(c: AlertChannelRecord) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "channel_type": c.channel_type,
        "config": c.config or {},
        "project": c.project,
        "triggers": c.triggers or [],
        "is_active": c.is_active,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


# ========================================
# Channel CRUD
# ========================================

@router.get("/channels")
def list_channels(db: Session = Depends(get_db)):
    """List all alert channels."""
    channels = db.query(AlertChannelRecord).order_by(AlertChannelRecord.created_at.desc()).all()
    return {"channels": [_channel_to_dict(c) for c in channels]}


@router.post("/channels", status_code=201)
def create_channel(data: ChannelCreate, db: Session = Depends(get_db)):
    channel = AlertChannelRecord(
        id=str(uuid.uuid4()),
        name=data.name,
        channel_type=data.channel_type,
        config=data.config,
        project=data.project,
        triggers=data.triggers,
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return _channel_to_dict(channel)


@router.put("/channels/{channel_id}")
def update_channel(channel_id: str, data: ChannelUpdate, db: Session = Depends(get_db)):
    channel = db.query(AlertChannelRecord).filter(AlertChannelRecord.id == channel_id).first()
    if not channel:
        raise HTTPException(404, "Channel not found")
    update = data.model_dump(exclude_unset=True)
    for k, v in update.items():
        setattr(channel, k, v)
    db.commit()
    db.refresh(channel)
    return _channel_to_dict(channel)


@router.delete("/channels/{channel_id}")
def delete_channel(channel_id: str, db: Session = Depends(get_db)):
    channel = db.query(AlertChannelRecord).filter(AlertChannelRecord.id == channel_id).first()
    if not channel:
        raise HTTPException(404, "Channel not found")

    # Cascade: remove this channel ID from any budget that references it
    budgets_with_channel = db.query(BudgetRecord).filter(
        BudgetRecord.alert_channel_ids.isnot(None)
    ).all()
    cleaned = 0
    for b in budgets_with_channel:
        ids = b.alert_channel_ids or []
        if channel_id in ids:
            b.alert_channel_ids = [x for x in ids if x != channel_id]
            cleaned += 1

    db.delete(channel)
    db.commit()
    return {"status": "deleted", "budgets_unmapped": cleaned}


@router.get("/channels/{channel_id}/budgets")
def list_budgets_for_channel(channel_id: str, db: Session = Depends(get_db)):
    """Return the budgets that fire alerts to this channel — used by the
    Alerts page to show 'Subscribed by N budgets' badge."""
    channel = db.query(AlertChannelRecord).filter(AlertChannelRecord.id == channel_id).first()
    if not channel:
        raise HTTPException(404, "Channel not found")

    # JSON column doesn't support indexed search in SQLite, so scan in Python
    candidates = db.query(BudgetRecord).filter(BudgetRecord.alert_channel_ids.isnot(None)).all()
    matched = [
        {
            "id": b.id,
            "name": b.name,
            "project": b.project,
            "period": b.period,
            "amount_usd": b.amount_usd,
        }
        for b in candidates
        if channel_id in (b.alert_channel_ids or [])
    ]
    return {"channel_id": channel_id, "count": len(matched), "budgets": matched}


@router.post("/channels/{channel_id}/test")
def test_channel(channel_id: str, db: Session = Depends(get_db)):
    """Send a test alert through a channel."""
    channel = db.query(AlertChannelRecord).filter(AlertChannelRecord.id == channel_id).first()
    if not channel:
        raise HTTPException(404, "Channel not found")

    result = _deliver_alert(
        channel,
        event_type="test",
        severity="info",
        message="Welcome to ObTrac",
        payload={"test": True, "timestamp": datetime.utcnow().isoformat()},
        db=db,
    )
    return result


# ========================================
# History
# ========================================

@router.get("/history")
def list_history(
    project: str = Query("all"),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(AlertHistoryRecord)
    if project != "all":
        query = query.filter(AlertHistoryRecord.project == project)
    history = query.order_by(AlertHistoryRecord.created_at.desc()).limit(limit).all()
    return {
        "history": [
            {
                "id": h.id,
                "project": h.project,
                "event_type": h.event_type,
                "severity": h.severity,
                "message": h.message,
                "payload": h.payload or {},
                "delivered": h.delivered,
                "response_status": h.response_status,
                "error": h.error,
                "created_at": h.created_at.isoformat() if h.created_at else None,
            }
            for h in history
        ]
    }


@router.get("/triggers")
def get_trigger_types():
    """Get available trigger event types."""
    return {"triggers": [{"id": k, "label": v} for k, v in TRIGGER_TYPES.items()]}


# ========================================
# Delivery (called from background)
# ========================================

def _format_slack_message(event_type: str, severity: str, message: str, payload: dict) -> dict:
    """Format a payload for Slack incoming webhook."""
    color = {"info": "#3aa8ff", "warning": "#f59e0b", "critical": "#ef4444"}.get(severity, "#666")
    icon = {"info": ":information_source:", "warning": ":warning:", "critical": ":rotating_light:"}.get(severity, ":bell:")

    fields = []
    for k, v in (payload or {}).items():
        if k in ("test", "timestamp"):
            continue
        fields.append({"title": k.replace("_", " ").title(), "value": str(v)[:200], "short": True})

    return {
        "text": f"{icon} *ObTrac Alert: {event_type}*",
        "attachments": [
            {
                "color": color,
                "text": message,
                "fields": fields,
                "footer": "ObTrac",
                "ts": int(datetime.utcnow().timestamp()),
            }
        ],
    }


def _deliver_alert(
    channel: AlertChannelRecord,
    event_type: str,
    severity: str,
    message: str,
    payload: dict,
    db: Session,
) -> dict:
    """Send an alert to a single channel and record history."""
    history = AlertHistoryRecord(
        id=str(uuid.uuid4()),
        channel_id=channel.id,
        project=payload.get("project", "all"),
        event_type=event_type,
        severity=severity,
        message=message,
        payload=payload,
    )
    db.add(history)
    db.commit()

    try:
        url = (channel.config or {}).get("url", "")
        if not url:
            raise ValueError("Channel has no URL configured")

        if channel.channel_type == "slack":
            body = _format_slack_message(event_type, severity, message, payload)
        else:
            # Generic webhook
            body = {
                "event_type": event_type,
                "severity": severity,
                "message": message,
                "payload": payload,
                "timestamp": datetime.utcnow().isoformat(),
            }

        headers = (channel.config or {}).get("headers", {}) or {}
        headers.setdefault("Content-Type", "application/json")

        resp = requests.post(url, json=body, headers=headers, timeout=10)
        history.delivered = resp.status_code < 400
        history.response_status = resp.status_code
        if not history.delivered:
            history.error = resp.text[:500]
        db.commit()

        return {
            "delivered": history.delivered,
            "status": resp.status_code,
            "channel": channel.name,
        }
    except Exception as e:
        history.error = str(e)[:500]
        db.commit()
        return {"delivered": False, "error": str(e), "channel": channel.name}


def check_and_fire_alerts(project: str, event_type: str, payload: dict, db: Session, severity: str = "warning", message: str = ""):
    """
    Check all active channels matching this project + event_type and fire alerts.
    Called from the background after trace ingestion.
    """
    channels = db.query(AlertChannelRecord).filter(
        AlertChannelRecord.is_active == True,
    ).all()

    fired = []
    for channel in channels:
        # Match project
        if channel.project != "all" and channel.project != project:
            continue
        # Match trigger
        if channel.triggers and event_type not in channel.triggers:
            continue

        result = _deliver_alert(
            channel,
            event_type=event_type,
            severity=severity,
            message=message or f"{event_type} fired for project {project}",
            payload=payload,
            db=db,
        )
        fired.append(result)

    return fired


def check_budget_alerts(project: str, db: Session):
    """
    After a trace is added, check if any budget thresholds are crossed.

    Per-budget channel routing:
      - If `budget.alert_channel_ids` is non-empty, fires alerts ONLY to those
        explicit channels (the new model).
      - Otherwise falls back to the legacy behavior: fire to any channel in
        the project that has the matching `budget_X` trigger.

    De-dup state:
      - `budget.last_fired_threshold` records the highest threshold already
        notified in the current period. We only fire when crossing to a NEW
        higher threshold, so a budget at 84% doesn't spam every trace.
      - The state resets automatically when the period rolls over (we detect
        this by comparing `last_fired_at` to the current period_start).
    """
    from app.api.budgets import _get_period_start

    budgets = db.query(BudgetRecord).filter(
        BudgetRecord.project == project,
        BudgetRecord.is_active == True,
    ).all()

    for budget in budgets:
        if budget.amount_usd <= 0:
            continue

        spent = _calculate_spent(db, budget.project, budget.period)
        used_pct = spent / budget.amount_usd * 100

        # Reset de-dup state if we're in a new period
        period_start = _get_period_start(budget.period)
        if budget.last_fired_at and budget.last_fired_at < period_start:
            budget.last_fired_threshold = None
            budget.last_fired_at = None
            db.commit()

        # Find the highest threshold that's been crossed
        thresholds = sorted(budget.alert_thresholds or [50, 80, 100], reverse=True)
        crossed: Optional[int] = None
        for t in thresholds:
            if used_pct >= t:
                crossed = t
                break

        if crossed is None:
            continue

        # De-dup: skip if we've already fired this threshold (or higher) this period
        if budget.last_fired_threshold is not None and crossed <= budget.last_fired_threshold:
            continue

        event = f"budget_{crossed}"
        severity = "critical" if crossed >= 100 else "warning" if crossed >= 80 else "info"
        msg = (
            f"Budget '{budget.name}' for project '{project}' is at {used_pct:.1f}% "
            f"(${spent:.2f} / ${budget.amount_usd:.2f})"
        )
        payload = {
            "project": project,
            "budget_id": budget.id,
            "budget_name": budget.name,
            "period": budget.period,
            "amount_usd": budget.amount_usd,
            "spent_usd": round(spent, 4),
            "used_pct": round(used_pct, 1),
            "threshold_crossed": crossed,
        }

        # Explicit per-budget mapping (new model)
        if budget.alert_channel_ids:
            channels = db.query(AlertChannelRecord).filter(
                AlertChannelRecord.id.in_(budget.alert_channel_ids),
                AlertChannelRecord.is_active == True,
            ).all()
            for ch in channels:
                _deliver_alert(ch, event, severity, msg, payload, db)
        else:
            # Legacy behavior: trigger-name matching
            check_and_fire_alerts(
                project=project,
                event_type=event,
                payload=payload,
                db=db,
                severity=severity,
                message=msg,
            )

        # Record the de-dup state
        budget.last_fired_threshold = crossed
        budget.last_fired_at = datetime.utcnow()
        db.commit()
