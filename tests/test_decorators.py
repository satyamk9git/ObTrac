"""
Tests for obtrac_sdk/decorators.py — root vs. child span detection and
framework-agnostic session-ID extraction. This is the core mechanism the
whole SDK depends on (README: "@trace auto-detects root vs. child").
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from obtrac_sdk import trace, obtrac_config
from obtrac_sdk.context import ObTracContext
from obtrac_sdk.decorators import _extract_session_id


@pytest.fixture(autouse=True)
def _isolated_config():
    """Point at an unreachable backend so trace-send threads fail silently
    (they're daemon threads and don't affect the calling code's return
    value) instead of hitting a real server during unit tests."""
    obtrac_config(project="pytest", backend_url="http://127.0.0.1:1", auto_create_project=False)
    yield


def test_root_trace_created_when_no_active_trace():
    @trace(name="root_fn", span_type="agent")
    def root_fn(x):
        assert ObTracContext.get_current_trace() is not None
        return x * 2

    assert ObTracContext.get_current_trace() is None
    result = root_fn(21)
    assert result == 42
    # Context is cleared after the call completes
    assert ObTracContext.get_current_trace() is None


def test_child_span_nests_under_root():
    seen_parent_trace_id = {}

    @trace(name="child_fn", span_type="tool_call")
    def child_fn():
        t = ObTracContext.get_current_trace()
        seen_parent_trace_id["child_saw"] = t.trace_id if t else None
        return "child result"

    @trace(name="root_fn", span_type="agent")
    def root_fn():
        t = ObTracContext.get_current_trace()
        seen_parent_trace_id["root_saw"] = t.trace_id
        return child_fn()

    root_fn()
    # The child span ran INSIDE the same root trace, not a separate one
    assert seen_parent_trace_id["child_saw"] == seen_parent_trace_id["root_saw"]
    assert seen_parent_trace_id["child_saw"] is not None


def test_exception_in_root_marks_trace_error_and_reraises():
    @trace(name="failing_root")
    def boom():
        raise ValueError("intentional test failure")

    with pytest.raises(ValueError, match="intentional test failure"):
        boom()
    # Context must be cleaned up even on the error path
    assert ObTracContext.get_current_trace() is None


@pytest.mark.asyncio
async def test_async_function_supported():
    @trace(name="async_root")
    async def async_fn(x):
        return x + 1

    result = await async_fn(1)
    assert result == 2


def test_session_id_from_kwarg():
    assert _extract_session_id((), {"session_id": "abc123"}) == "abc123"


def test_session_id_from_dict_arg():
    assert _extract_session_id(({"thread_id": "t-1"},), {}) == "t-1"


def test_session_id_from_langgraph_configurable_convention():
    config_arg = {"configurable": {"thread_id": "lg-thread-9"}}
    assert _extract_session_id((config_arg,), {}) == "lg-thread-9"


def test_session_id_from_nested_session_object():
    class FakeSession:
        id = "adk-session-42"

    class FakeContext:
        session = FakeSession()

    assert _extract_session_id((FakeContext(),), {}) == "adk-session-42"


def test_session_id_none_when_absent():
    assert _extract_session_id(("just a string arg",), {"other_kwarg": 1}) is None
