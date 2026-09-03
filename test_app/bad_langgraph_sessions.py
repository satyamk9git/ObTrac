"""
ObTrac + LangGraph — multi-session stress test for the bad-rag-demo project.

This does NOT modify bad_langgraph_app.py. It imports its already-tuned
pipeline (corpus loading, FAISS retrieval, LangGraph graph, _LiteLLMChat
shim, obtrac_config wiring) and drives it through 10 additional sessions
covering three distinct failure/success modes:

  1. "adjacent"   — same entity/topic, different time period or attribute
                    never stated in the Q3-2026-only corpus. Proven to
                    induce low faithfulness/context_precision/context_recall.
  2. "in_scope"   — questions genuinely answerable from the corpus, to get
                    a real score spread (not uniformly near-zero).
  3. "multi_turn" — 2-3 turns sharing one session_id, later turns referring
                    back to "that"/"it" from the prior turn, to exercise
                    ObTrac's Sessions page grouping.

Each session gets its own session_id (varied per session, not the single
module-level SESSION_ID that bad_langgraph_app.py sets at import time) by
re-calling obtrac_config() before that session's questions — the SDK's
@trace decorator prefers cfg.session_id over anything auto-detected from
call args, so this is the correct way to vary it per session in a script
that doesn't touch the app's own pipeline code.

Run:
    source .venv/bin/activate
    python test_app/bad_langgraph_sessions.py
"""
import os
import sys
import time
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obtrac_sdk import obtrac_config

from test_app import bad_langgraph_app as bla

LOG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "session_run_log.json"
)

RUN_TAG = int(time.time())

# ---------------------------------------------------------------------------
# Session definitions
# ---------------------------------------------------------------------------
# Each session: {"tag": failure-mode label, "questions": [{"query", "ground_truth"}]}

NOT_STATED = "Not stated in the document — {reason}"

SESSIONS = [
    {
        "tag": "adjacent",
        "note": "prior-year / full-year figures not in the Q3-2026-only corpus",
        "questions": [
            {
                "query": "What was Solstice Robotics' total revenue for full-year 2025?",
                "ground_truth": "Not stated in the document — the corpus covers only Q3 2026 (Jul-Sep 2026) and reports no full-year 2025 figures.",
            },
            {
                "query": "What was Solstice's gross margin in Q1 2026?",
                "ground_truth": "Not stated in the document — only Q3 2026 gross margin (61%) is reported; no Q1 2026 figures appear in this corpus.",
            },
            {
                "query": "How did Solstice's R&D spending in Q3 2026 compare to R&D spending in Q3 2025?",
                "ground_truth": "Not stated in the document — no Q3 2025 R&D figures are given for comparison; only the Q3 2026 R&D spend of $11.2 million appears.",
            },
        ],
    },
    {
        "tag": "adjacent",
        "note": "competitor / market-share questions never named in the corpus",
        "questions": [
            {
                "query": "Which competitors does Solstice Robotics consider its biggest threat in the warehouse automation market?",
                "ground_truth": "Not stated in the document — the corpus only refers generically to 'competition from other automation vendors' in the risk factors section and names no specific competitors.",
            },
            {
                "query": "What market share percentage does Solstice hold in the warehouse robotics industry?",
                "ground_truth": "Not stated in the document — no market share percentage or industry-wide market data is reported anywhere in this corpus.",
            },
        ],
    },
    {
        "tag": "adjacent",
        "note": "future-quarter/year guidance beyond the disclosed Q4 2026 outlook",
        "questions": [
            {
                "query": "What is Solstice Robotics' revenue guidance for fiscal year 2027?",
                "ground_truth": "Not stated in the document — the only forward guidance given is for Q4 2026 ($61-64 million); no FY2027 guidance appears.",
            },
            {
                "query": "How many AetherArm-7 units does Solstice expect to ship in Q1 2027?",
                "ground_truth": "Not stated in the document — unit-shipment guidance is given only for Q4 2026 (1,300-1,400 units); no Q1 2027 figures appear.",
            },
            {
                "query": "What new product lines is Solstice planning to launch in 2027?",
                "ground_truth": "Not stated in the document — future product lines are described only as 'still in early internal design review and not yet ready for disclosure,' with no 2027 launch details given.",
            },
            {
                "query": "What is Solstice's projected net income for Q4 2026?",
                "ground_truth": "Not stated in the document — the Q4 2026 outlook gives revenue and unit-shipment ranges only; no net income projection is disclosed.",
            },
        ],
    },
    {
        "tag": "adjacent",
        "note": "headcount / funding / named-CEO — attributes never disclosed",
        "questions": [
            {
                "query": "How many employees does Solstice Robotics have in total?",
                "ground_truth": "Not stated in the document — no total employee headcount figure appears anywhere in this corpus.",
            },
            {
                "query": "When did Solstice Robotics complete its most recent funding round, and how much did it raise?",
                "ground_truth": "Not stated in the document — no funding round, investor, or fundraising information appears in this earnings summary.",
            },
            {
                "query": "Who is Solstice Robotics' Chief Executive Officer?",
                "ground_truth": "Not stated by name in the document — the CEO is quoted only anonymously as 'the company's Chief Executive Officer,' with no name given.",
            },
        ],
    },
    {
        "tag": "in_scope",
        "note": "directly answerable Q3 2026 financial facts",
        "questions": [
            {
                "query": "What was Solstice Robotics' total revenue in Q3 2026?",
                "ground_truth": "Solstice Robotics reported Q3 2026 revenue of $58.4 million.",
            },
            {
                "query": "What was Solstice's net income for Q3 2026?",
                "ground_truth": "Solstice Robotics reported Q3 2026 net income of $6.1 million.",
            },
            {
                "query": "How many AetherArm-7 units did Solstice ship during Q3 2026?",
                "ground_truth": "Solstice shipped 1,240 AetherArm-7 units during Q3 2026.",
            },
            {
                "query": "What was Solstice's customer churn rate in Q3 2026?",
                "ground_truth": "Q3 2026 customer churn was 3.2%.",
            },
        ],
    },
    {
        "tag": "in_scope",
        "note": "directly answerable Q3 2026 operational facts",
        "questions": [
            {
                "query": "Where is Solstice Robotics' manufacturing facility located?",
                "ground_truth": "Solstice's single manufacturing facility is located in Reno, Nevada.",
            },
            {
                "query": "What three new customers signed multi-unit deployment agreements with Solstice during Q3 2026?",
                "ground_truth": "LogiCore Distribution, Fenwick Freight Systems, and Turnkey Pallet Co. signed multi-unit deployment agreements during Q3 2026.",
            },
            {
                "query": "What is Solstice's revenue outlook for Q4 2026?",
                "ground_truth": "Management's internal outlook for Q4 2026 is revenue between $61 million and $64 million.",
            },
        ],
    },
    {
        "tag": "multi_turn",
        "note": "in-scope opener, then two adjacent-period follow-ups referencing 'that'",
        "questions": [
            {
                "query": "What was Solstice Robotics' revenue in Q3 2026?",
                "ground_truth": "Solstice Robotics reported Q3 2026 revenue of $58.4 million.",
            },
            {
                "query": "How does that number compare to the same quarter last year?",
                "ground_truth": "Not stated in the document — no Q3 2025 revenue figure is given for a year-over-year comparison.",
            },
            {
                "query": "What drove the change compared to last year?",
                "ground_truth": "Not stated in the document — no prior-year commentary or year-over-year drivers are discussed in this corpus.",
            },
        ],
    },
    {
        "tag": "multi_turn",
        "note": "in-scope opener, one adjacent follow-up",
        "questions": [
            {
                "query": "What was Solstice's gross margin in Q3 2026?",
                "ground_truth": "Solstice reported a Q3 2026 gross margin of 61%.",
            },
            {
                "query": "Is that higher or lower than their Q2 2026 gross margin?",
                "ground_truth": "Not stated in the document — no Q2 2026 gross margin figure is reported for comparison.",
            },
        ],
    },
    {
        "tag": "multi_turn",
        "note": "in-scope opener, adjacent follow-up, back to in-scope",
        "questions": [
            {
                "query": "How many active warehouse deployments did Solstice have at the end of Q3 2026?",
                "ground_truth": "Solstice ended Q3 2026 with 187 active warehouse deployments.",
            },
            {
                "query": "How many of those did they add compared to the prior quarter, Q2 2026?",
                "ground_truth": "Not stated in the document — no Q2 2026 deployment count is given, so the quarter-over-quarter change cannot be determined from this corpus.",
            },
            {
                "query": "And what was the median field service response time in Q3 2026?",
                "ground_truth": "The Columbus service depot's median technician response time in Q3 2026 was 1.8 business days.",
            },
        ],
    },
    {
        "tag": "adjacent",
        "note": "attribute types never disclosed (geography breakdown, stock performance)",
        "questions": [
            {
                "query": "What percentage of Solstice's warehouse deployments are located outside North America?",
                "ground_truth": "Not stated in the document — deployments are described only as sold 'primarily to mid-size third-party logistics warehouses... across North America,' with no international breakdown or percentage given.",
            },
            {
                "query": "What was Solstice's stock price performance during Q3 2026?",
                "ground_truth": "Not stated in the document — this is an internal earnings summary with no stock price, market capitalization, or share performance data.",
            },
        ],
    },
]


def main():
    print(f"Loading corpus from {bla.CORPUS_PATH} ...")
    bla.VECTORSTORE, n_chunks = bla.build_bad_index(bla.CORPUS_PATH)
    print(f"Indexed {n_chunks} chunks (chunk_size=2000, chunk_overlap=0, k=2 at query time)\n")

    total_questions = sum(len(s["questions"]) for s in SESSIONS)
    print(f"Running {len(SESSIONS)} sessions, {total_questions} questions total.\n")

    log = []
    q_counter = 0

    for si, sess in enumerate(SESSIONS, start=1):
        session_id = f"bad_sess_{si}_{sess['tag']}_{RUN_TAG}"
        print(f"=== Session {si}/{len(SESSIONS)} [{sess['tag']}] session_id={session_id} ===")
        print(f"    note: {sess['note']}")

        # Re-point the global ObTrac config at this session's id. Reuses the
        # exact same project/backend/user/auto_eval/default_metrics that
        # bad_langgraph_app.py already established — only session_id changes.
        obtrac_config(
            project="bad-rag-demo",
            backend_url="http://localhost:8100",
            user="satyam",
            auto_eval=True,
            default_metrics=bla.RAG_EVAL_METRICS,
            session_id=session_id,
        )

        for qi, item in enumerate(sess["questions"], start=1):
            q_counter += 1
            q = item["query"]
            gt = item["ground_truth"]
            print(f"  [{qi}/{len(sess['questions'])}] Q: {q}")
            t0 = time.time()
            entry = {
                "global_index": q_counter,
                "session_index": si,
                "session_id": session_id,
                "tag": sess["tag"],
                "note": sess["note"],
                "turn": qi,
                "query": q,
                "ground_truth": gt,
            }
            try:
                answer = bla.run_pipeline(q, ground_truth=gt)
                elapsed = time.time() - t0
                entry["answer"] = answer
                entry["elapsed_s"] = round(elapsed, 2)
                entry["error"] = None
                print(f"      A ({elapsed:.1f}s): {answer[:200]}")
            except Exception as e:
                entry["answer"] = None
                entry["elapsed_s"] = round(time.time() - t0, 2)
                entry["error"] = f"{type(e).__name__}: {e}"
                print(f"      ERROR: {entry['error']}")
            log.append(entry)
            time.sleep(2)  # small gap between root traces within a session

        print(f"  Session {si} done. Sleeping 9s for background auto-eval to keep up...\n")
        time.sleep(9)

    with open(LOG_PATH, "w") as f:
        json.dump(log, f, indent=2)
    print(f"Wrote run log ({len(log)} entries) to {LOG_PATH}")

    print("\nNow check:")
    print("  curl 'http://localhost:8100/api/v1/traces?project=bad-rag-demo&limit=100'")
    print("  curl 'http://localhost:8100/api/v1/metrics/summary?project=bad-rag-demo&limit=100'")


if __name__ == "__main__":
    main()
