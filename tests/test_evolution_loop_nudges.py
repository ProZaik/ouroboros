import pytest
from ouroboros.loop_nudges import (
    rounds_since_last_mutative_call,
    _maybe_inject_evolution_deadline,
    _maybe_inject_plan_review_directive,
)

def test_rounds_since_last_mutative_call_empty():
    assert rounds_since_last_mutative_call(None, 10) == 10
    assert rounds_since_last_mutative_call({}, 10) == 10
    assert rounds_since_last_mutative_call({"tool_calls": []}, 10) == 10

def test_rounds_since_last_mutative_call_with_round_id():
    llm_trace = {
        "tool_calls": [
            {"tool": "read_file", "round_id": "exec_abc:round:1"},
            {"tool": "edit_text", "round_id": "exec_abc:round:4"},
            {"tool": "search_code", "round_id": "exec_abc:round:6"},
        ]
    }
    # Current round is 9, last mutation at 4 -> 5 rounds since mutation
    assert rounds_since_last_mutative_call(llm_trace, 9) == 5

def test_rounds_since_last_mutative_call_ignores_errors():
    llm_trace = {
        "tool_calls": [
            {"tool": "edit_text", "round_id": "exec_abc:round:4", "is_error": True},
        ]
    }
    # Error mutation does not count
    assert rounds_since_last_mutative_call(llm_trace, 9) == 9

def test_evolution_deadline_injected():
    messages = []
    accumulated_usage = {}
    llm_trace = {
        "tool_calls": [
            {"tool": "read_file", "round_id": "exec_abc:round:1"},
        ]
    }
    fired = _maybe_inject_evolution_deadline(
        10, messages, accumulated_usage, llm_trace=llm_trace, task_type="evolution"
    )
    assert fired is True
    assert len(messages) == 1
    assert "[DECIDE-OR-ABSTAIN DEADLINE" in messages[0]["content"]

def test_evolution_deadline_not_injected_non_evolution():
    messages = []
    accumulated_usage = {}
    fired = _maybe_inject_evolution_deadline(
        10, messages, accumulated_usage, llm_trace={}, task_type="ordinary"
    )
    assert fired is False
    assert len(messages) == 0

def test_evolution_deadline_not_injected_if_recent_mutation():
    messages = []
    accumulated_usage = {}
    llm_trace = {
        "tool_calls": [
            {"tool": "edit_text", "round_id": "exec_abc:round:8"},
        ]
    }
    fired = _maybe_inject_evolution_deadline(
        10, messages, accumulated_usage, llm_trace=llm_trace, task_type="evolution"
    )
    assert fired is False


def test_evolution_deadline_notice_names_the_residual_pin_exit():
    """A falsified objective must convert into a residual-pin commit, not a no-op.

    Reviewer FAIL on cycle #79: the notices only offered two exits (mutate /
    abstain), so cycles #76-#78 each read the instruction correctly and
    abstained. The third exit is now typed into the notice text itself.
    """
    messages = []
    accumulated_usage = {}
    llm_trace = {
        "tool_calls": [
            {"tool": "read_file", "round_id": "exec_abc:round:1"},
        ]
    }
    fired = _maybe_inject_evolution_deadline(
        10, messages, accumulated_usage, llm_trace=llm_trace, task_type="evolution"
    )
    assert fired is True
    text = messages[0]["content"]
    assert "RESIDUAL PIN" in text
    assert "3." in text


def test_evolution_crux_directive_names_residual_pin_for_falsified_objective():
    """The round-1 crux directive names the residual-pin default, not bare exit."""
    from ouroboros.loop_nudges import _maybe_inject_evolution_crux_directive

    messages = []
    accumulated_usage = {}
    fired = _maybe_inject_evolution_crux_directive(
        1, messages, accumulated_usage, task_type="evolution"
    )
    assert fired is True
    text = messages[0]["content"]
    assert "RESIDUAL PIN" in text
    assert "NO_OP" in text

def test_plan_review_directive_injected():
    messages = []
    accumulated_usage = {}
    llm_trace = {
        "tool_calls": [
            {"tool": "plan_task", "round_id": "exec_abc:round:2", "result": "REVISE_PLAN: needs test coverage"},
            {"tool": "read_file", "round_id": "exec_abc:round:3"},
        ]
    }
    fired = _maybe_inject_plan_review_directive(
        3, messages, accumulated_usage, llm_trace=llm_trace
    )
    assert fired is True
    assert len(messages) == 1
    assert "[PLAN-REVIEW ACTION REQUIRED]" in messages[0]["content"]

def test_plan_review_directive_not_injected_after_mutation():
    messages = []
    accumulated_usage = {}
    llm_trace = {
        "tool_calls": [
            {"tool": "plan_task", "round_id": "exec_abc:round:2", "result": "REVISE_PLAN: needs test coverage"},
            {"tool": "edit_text", "round_id": "exec_abc:round:3"},
        ]
    }
    fired = _maybe_inject_plan_review_directive(
        4, messages, accumulated_usage, llm_trace=llm_trace
    )
    assert fired is False
