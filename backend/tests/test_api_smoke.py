"""
Smoke tests across the core API surface, against an isolated throwaway
SQLite DB (see conftest.py) — never the real obtrac.db.
"""


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


def test_root(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "version" in r.json()


def test_create_and_get_project(client):
    r = client.post("/api/v1/traces/projects", json={"name": "pytest-project", "description": "test"})
    assert r.status_code == 201
    assert r.json()["name"] == "pytest-project"

    # Idempotent — creating again returns already_existed=True, not an error
    r2 = client.post("/api/v1/traces/projects", json={"name": "pytest-project"})
    assert r2.status_code == 201
    assert r2.json()["already_existed"] is True


def test_create_and_fetch_trace(client):
    payload = {
        "project": "pytest-project",
        "name": "test_pipeline",
        "status": "success",
        "query": "what is 2+2",
        "answer": "4",
        "context": "math facts",
        "total_latency_ms": 123.4,
        "total_cost_usd": 0.001,
        "spans": [
            {
                "name": "generate",
                "span_type": "generation",
                "status": "success",
                "inputs": {"q": "what is 2+2"},
                "outputs": {"result": "4"},
                "tokens": {"prompt": 10, "completion": 2},
                "cost_usd": 0.001,
                "model": "claude-sonnet-5",
            }
        ],
    }
    r = client.post("/api/v1/traces", json=payload)
    assert r.status_code == 201
    trace_id = r.json()["trace_id"]

    r2 = client.get(f"/api/v1/traces/{trace_id}")
    assert r2.status_code == 200
    body = r2.json()
    assert body["query"] == "what is 2+2"
    assert len(body["spans"]) == 1
    assert body["spans"][0]["model"] == "claude-sonnet-5"


def test_get_nonexistent_trace_404s(client):
    r = client.get("/api/v1/traces/does-not-exist")
    assert r.status_code == 404


def test_llm_config_create_masks_api_key_in_list(client):
    r = client.post("/api/v1/llm-configs", json={
        "name": "pytest-llm",
        "provider": "anthropic",
        "model_id": "claude-sonnet-5",
        "api_key": "sk-ant-secret-value-should-not-leak",
    })
    assert r.status_code == 201
    body = r.json()
    assert "api_key" not in body  # only api_key_masked should be present
    assert "sk-ant-secret-value-should-not-leak" not in str(body)

    r2 = client.get("/api/v1/llm-configs")
    assert "sk-ant-secret-value-should-not-leak" not in r2.text


def test_sql_editor_select_works(client):
    r = client.post("/api/v1/sql/execute", json={"query": "SELECT 1 as one"})
    assert r.status_code == 200
    body = r.json()
    assert body["rows"] == [{"one": 1}]


def test_sql_editor_blocks_writes_at_driver_level(client):
    """The core security fix: write attempts fail regardless of phrasing,
    because the connection itself is opened read-only — not because a
    keyword blocklist happened to catch this specific verb."""
    r = client.post("/api/v1/sql/execute", json={
        "query": "UPDATE llm_configs SET name='pwned' WHERE 1=1",
    })
    assert r.status_code == 200  # endpoint itself doesn't 500
    body = r.json()
    assert "error" in body
    assert body["rows"] == []


def test_sql_editor_blocks_delete_too(client):
    r = client.post("/api/v1/sql/execute", json={"query": "DELETE FROM traces"})
    body = r.json()
    assert "error" in body


def test_evaluation_metrics_info(client):
    r = client.get("/api/v1/evaluation/metrics-info")
    assert r.status_code == 200
    metrics = r.json()["metrics"]
    assert "faithfulness" in metrics
    assert "context_precision" in metrics
    # Regression check for the needs_ground_truth bug fix: context_precision
    # must NOT require ground truth, since app/services/llm_judge.py's
    # actual prompt only needs question+context.
    assert metrics["context_precision"]["needs_ground_truth"] is False
