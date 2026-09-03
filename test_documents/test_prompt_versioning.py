"""
Exercises the prompt registry's versioning + AI-merge features against the
"rag_answer" prompt already registered by test_app/prompts_setup.py:

  1. Create v2 — a stricter variant (explicit "cite exact source phrase")
  2. Create v3 — a different variant (explicit max-length constraint)
  3. Read back full lineage
  4. Activate v2 (so /latest changes)
  5. Merge v2 + v3 with the Claude LLM -> draft
  6. Approve the draft -> creates v4
  7. Verify v4 is now active and readable via get_prompt()
"""
import json
import requests

BACKEND = "http://localhost:8100/api/v1"
NAME = "rag_answer"


def show(label, resp):
    print(f"\n--- {label} (HTTP {resp.status_code}) ---")
    try:
        data = resp.json()
        print(json.dumps(data, indent=2)[:1500])
        return data
    except Exception:
        print(resp.text[:500])
        return None


# 1. Create v2
v2 = show("Create v2 (stricter)", requests.post(f"{BACKEND}/prompts/{NAME}/versions", json={
    "template": (
        "You are a helpful assistant. Answer the question based ONLY on the provided context.\n"
        "Quote the exact phrase from the context that supports your answer.\n"
        "If the context does not contain enough information, say 'I don't have enough information to answer that.'\n\n"
        "Context:\n{{context}}\n\nQuestion: {{question}}\n\n"
        "Answer clearly and concisely in 2-4 sentences, then add a line starting with 'Source: ' quoting the supporting text."
    ),
    "commit_message": "v2 — require explicit source quoting to reduce hallucination",
}))

# 2. Create v3
v3 = show("Create v3 (concise + length cap)", requests.post(f"{BACKEND}/prompts/{NAME}/versions", json={
    "template": (
        "You are a helpful assistant. Answer the question based ONLY on the provided context.\n"
        "If the context does not contain enough information, say 'I don't have enough information to answer that.'\n\n"
        "Context:\n{{context}}\n\nQuestion: {{question}}\n\n"
        "Answer in ONE sentence. No more than 30 words. Be direct."
    ),
    "commit_message": "v3 — enforce single-sentence, 30-word cap for latency/cost",
}))

# 3. Full lineage
lineage = show("Full lineage", requests.get(f"{BACKEND}/prompts/{NAME}"))
if lineage:
    print(f"\nVersion count: {lineage.get('version_count')} | active_version: {lineage.get('active_version')}")

# 4. Activate v2
show("Activate v2", requests.post(f"{BACKEND}/prompts/{NAME}/versions/2/activate"))
latest = show("GET /latest after activating v2", requests.get(f"{BACKEND}/prompts/{NAME}/latest"))

# 5. Get the Claude LLM config id for the merge
configs = requests.get(f"{BACKEND}/llm-configs").json()["configs"]
claude_cfg = next((c for c in configs if c["provider"] == "anthropic"), None)
if not claude_cfg:
    print("\nERROR: no anthropic LLM config found — cannot run merge test")
else:
    print(f"\nUsing LLM config: {claude_cfg['name']} ({claude_cfg['model_id']}) id={claude_cfg['id']}")

    merge_resp = requests.post(f"{BACKEND}/prompts/{NAME}/merge", json={
        "versions": [2, 3],
        "llm_config_id": claude_cfg["id"],
        "extra_instructions": "Keep the source-quoting requirement from the stricter version, but also keep answers under 3 sentences for cost efficiency.",
    })
    draft = show("Merge v2 + v3 via Claude", merge_resp)

    if draft and "draft_id" in draft:
        draft_id = draft["draft_id"]
        print(f"\nMerged template preview:\n{draft.get('merged_template', '')[:400]}")
        print(f"Missing vars: {draft.get('missing_variables')}  Extra vars: {draft.get('extra_variables')}")

        # 6. Approve the draft -> creates v4
        approved = show("Approve draft -> new version", requests.post(
            f"{BACKEND}/prompts/drafts/{draft_id}/approve",
            json={"commit_message": "v4 — AI-merged: source quoting + concise cost-efficient style"},
        ))

        # 7. Confirm v4 is now active
        final = show("Final lineage after merge+approve", requests.get(f"{BACKEND}/prompts/{NAME}"))
        if final:
            print(f"\nFinal state: version_count={final.get('version_count')} active_version={final.get('active_version')}")
    else:
        print("\nMerge failed — see response above (likely an LLM call error, e.g. sampling-param rejection).")

print("\n=== Prompt versioning + AI merge test complete ===")
