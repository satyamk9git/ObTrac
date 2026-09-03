"""
Regression tests for app/api/explain.py::_parse_llm_json — this is the exact
bug that produced "Analysis returned in non-JSON format" in the dashboard:
a complete, valid JSON response got cut off mid-generation because
max_tokens was too low, and the naive json.loads() failed on the whole
thing instead of salvaging what was complete.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.api.explain import _parse_llm_json


def test_parses_complete_json():
    text = '{"health": "good", "headline": "all clear"}'
    result = _parse_llm_json(text)
    assert result == {"health": "good", "headline": "all clear"}


def test_strips_markdown_code_fences():
    text = '```json\n{"a": 1}\n```'
    assert _parse_llm_json(text) == {"a": 1}


def test_recovers_truncated_array_mid_object():
    """Mirrors the actual production failure: a response cut off mid-string
    inside the second element of a top_issues array. Recovery should keep
    the complete first element and drop the incomplete second one."""
    truncated = (
        '{"health": "critical", "top_issues": ['
        '{"metric": "context_precision", "severity": "high"}, '
        '{"metric": "answer_relevancy", "severity": "med'  # <-- cut off mid-string
    )
    result = _parse_llm_json(truncated)
    assert result is not None
    assert result["health"] == "critical"
    assert len(result["top_issues"]) == 1
    assert result["top_issues"][0]["metric"] == "context_precision"


def test_recovers_truncated_after_last_complete_key():
    truncated = '{"a": 1, "b": 2, "c": "incomple'
    result = _parse_llm_json(truncated)
    assert result == {"a": 1, "b": 2}


def test_returns_none_for_garbage_with_nothing_salvageable():
    assert _parse_llm_json("not json at all, no braces") is None


def test_returns_none_for_truncation_before_any_comma():
    """No safe cut point exists yet — nothing to salvage."""
    assert _parse_llm_json('{"onlykey": "no comma yet, still going') is None
