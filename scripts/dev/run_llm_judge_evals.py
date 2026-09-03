"""
Runs real evaluation on every generated trace using ObTrac's built-in
LLM-as-Judge service (app.services.llm_judge) instead of the RAGAS HTTP
endpoint — RAGAS's own package currently has a broken internal import
(langchain_community.chat_models.vertexai.ChatVertexAI, removed upstream)
that isn't fixable by simple version pinning without breaking langgraph.

Must be run with backend/ on the path (so `app.*` imports resolve), same
as how uvicorn runs the backend itself. Writes scores + suggestions
straight into TraceRecord via SQLAlchemy, matching what /evaluation/run
would have written.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "backend"))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # for obtrac_sdk

from app.db.database import SessionLocal
from app.db.models import TraceRecord, LLMConfigRecord
from app.services.llm_judge import evaluate_with_llm_judge
from obtrac_sdk.evaluator import SuggestionEngine

with open(os.path.join(os.path.dirname(__file__), "session_log.json")) as f:
    log = json.load(f)

db = SessionLocal()

claude_cfg = db.query(LLMConfigRecord).filter(LLMConfigRecord.provider == "anthropic").first()
if not claude_cfg:
    print("ERROR: no anthropic LLM config found")
    sys.exit(1)
print(f"Judge: {claude_cfg.name} ({claude_cfg.provider}/{claude_cfg.model_id})\n")

traces = (
    db.query(TraceRecord)
    .filter(TraceRecord.project == "langgraph-agent", TraceRecord.session_id != None, TraceRecord.session_id != "")
    .order_by(TraceRecord.created_at.asc())
    .all()
)

by_session = {}
for t in traces:
    by_session.setdefault(t.session_id, []).append(t)

log_by_session = {}
for entry in log:
    log_by_session.setdefault(entry["session"], []).append(entry)

pairs = []
for sid, entries in log_by_session.items():
    rows = by_session.get(sid, [])
    for row, entry in zip(rows, entries):
        pairs.append((row, entry))

print(f"{len(pairs)} traces to evaluate\n")

engine = SuggestionEngine()
results = []

for i, (trace, entry) in enumerate(pairs):
    if trace.status == "error" or entry["note"].startswith("error"):
        print(f"[{i+1}/{len(pairs)}] SKIP {trace.trace_id[:8]} (error trace)")
        continue

    metrics = ["faithfulness", "answer_relevancy"]
    gt = entry.get("ground_truth")
    if trace.context:
        metrics.append("context_precision")
    if gt:
        metrics.append("answer_correctness")

    print(f"[{i+1}/{len(pairs)}] {trace.trace_id[:8]} | {entry['note'][:55]:55s} | {metrics}")

    try:
        result = evaluate_with_llm_judge(
            llm_config=claude_cfg,
            question=trace.query or "",
            answer=trace.answer or "",
            context=trace.context or "",
            ground_truth=gt or "",
            metrics=metrics,
        )
        scores = result["metrics"]
        reasons = result["reasons"]
    except Exception as e:
        print(f"      EXCEPTION: {type(e).__name__}: {e}")
        scores, reasons = {}, {}

    print(f"      -> scores={scores}")

    suggestions = engine.generate_suggestions(scores) if scores else []

    trace.metrics = scores
    trace.suggestions = suggestions
    db.commit()

    results.append({
        "trace_id": trace.trace_id, "session": entry["session"], "note": entry["note"],
        "question": entry["question"], "ground_truth": gt,
        "scores": scores, "reasons": reasons, "suggestions": suggestions,
    })
    time.sleep(0.3)

db.close()

with open(os.path.join(os.path.dirname(__file__), "eval_results.json"), "w") as f:
    json.dump(results, f, indent=2)

print(f"\nDone. {len(results)} traces evaluated and written to the DB.")
print("Wrote scripts/dev/eval_results.json")

print("\n=== Failure-scenario scores ===")
for r in results:
    if any(k in r["note"] for k in ("hallucination_bait", "false_premise", "bad_ground_truth", "out_of_domain", "needle")):
        print(f"\n- [{r['session']}] {r['question'][:65]}")
        print(f"    note: {r['note']}")
        print(f"    scores: {r['scores']}")
        for m, reason in r["reasons"].items():
            print(f"    {m} reason: {reason}")
