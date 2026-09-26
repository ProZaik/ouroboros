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


def test_evolution_exit_contract_unification_ssot(monkeypatch):
    """ibl-ea1b0e202f90 (A2): verify all three evolution notice builders render EVOLUTION_EXIT_CONTRACT."""
    from ouroboros.loop_nudges import (
        EVOLUTION_EXIT_CONTRACT,
        _maybe_inject_evolution_deadline,
        _maybe_inject_evolution_crux_directive,
    )
    import supervisor.evolution_lifecycle as lifecycle

    # 1. Deadline producer
    msgs1 = []
    _maybe_inject_evolution_deadline(
        10,
        msgs1,
        {},
        llm_trace={"tool_calls": [{"tool": "read_file", "round_id": "exec_abc:round:1"}]},
        task_type="evolution",
    )
    assert len(msgs1) == 1
    assert EVOLUTION_EXIT_CONTRACT in msgs1[0]["content"]

    # 2. Crux directive producer
    msgs2 = []
    _maybe_inject_evolution_crux_directive(1, msgs2, {}, task_type="evolution")
    assert len(msgs2) == 1
    assert EVOLUTION_EXIT_CONTRACT in msgs2[0]["content"]

    # 3. Supervisor evolution lifecycle producer (fires when >= 3 consecutive no-ops)
    fake_campaign = {
        "status": "active",
        "objective": "Test unify exit contract",
        "history": [
            {"task_id": "t1", "transaction": {"cycle_outcome": "no_op", "no_op_reason": "r1"}},
            {"task_id": "t2", "transaction": {"cycle_outcome": "no_op", "no_op_reason": "r2"}},
            {"task_id": "t3", "transaction": {"cycle_outcome": "no_op", "no_op_reason": "r3"}},
        ],
    }
    monkeypatch.setattr(lifecycle, "_read_evolution_campaign", lambda: fake_campaign)
    monkeypatch.setattr(lifecycle, "_evolution_target_preflight", lambda obj, st: (obj, st, ""))
    txt = lifecycle.build_evolution_task_text(4)
    assert "MANDATORY FALSIFY-OR-CLOSE DIRECTIVE" in txt
    assert EVOLUTION_EXIT_CONTRACT in txt


def test_evolution_decision_step_residual_pin_enforcement():
    """ibl-eacad98b3b83 (A4): verified typed bounded decision step for falsified objective with residual owed."""
    from ouroboros.loop_nudges import (
        EvolutionDecisionStep,
        record_evolution_falsification,
        get_evolution_decision_step,
        _maybe_inject_evolution_deadline,
    )

    accumulated_usage = {}
    step = record_evolution_falsification(
        accumulated_usage,
        reason="Symbol already implemented in v7.4.15",
        residual_owed=True,
        target="tests/test_foo.py",
    )
    assert isinstance(step, EvolutionDecisionStep)
    assert step.exit_type == "residual_pin"
    assert step.falsified is True
    assert step.residual_owed is True
    assert get_evolution_decision_step(accumulated_usage) == step

    messages = []
    llm_trace = {"tool_calls": [{"tool": "read_file", "round_id": "exec_abc:round:1"}]}
    fired = _maybe_inject_evolution_deadline(
        10, messages, accumulated_usage, llm_trace=llm_trace, task_type="evolution"
    )
    assert fired is True
    text = messages[0]["content"]
    assert "[BOUNDED DECISION DEADLINE" in text
    assert "LAND THE RESIDUAL PIN" in text
    assert "Do not conclude as an ungrounded NO_OP" in text


def test_evolution_decision_step_no_residual_owed_enforcement():
    """ibl-eacad98b3b83 (A4): verified bounded decision step for falsified objective when no residual owed."""
    from ouroboros.loop_nudges import (
        record_evolution_falsification,
        _maybe_inject_evolution_deadline,
    )

    accumulated_usage = {}
    record_evolution_falsification(
        accumulated_usage,
        reason="Non-existent API removed 6 months ago, no legacy seam left",
        residual_owed=False,
    )

    messages = []
    llm_trace = {"tool_calls": [{"tool": "read_file", "round_id": "exec_abc:round:1"}]}
    fired = _maybe_inject_evolution_deadline(
        10, messages, accumulated_usage, llm_trace=llm_trace, task_type="evolution"
    )
    assert fired is True
    text = messages[0]["content"]
    assert "[BOUNDED DECISION DEADLINE" in text
    assert "conclude this cycle with an explicit, named NO_OP" in text
    assert "Non-existent API removed 6 months ago" in text


def test_crux_directive_initializes_decision_step():
    """ibl-eacad98b3b83 (A4): crux directive registers initial undecided EvolutionDecisionStep."""
    from ouroboros.loop_nudges import (
        get_evolution_decision_step,
        _maybe_inject_evolution_crux_directive,
    )

    accumulated_usage = {}
    messages = []
    fired = _maybe_inject_evolution_crux_directive(1, messages, accumulated_usage, task_type="evolution")
    assert fired is True
    step = get_evolution_decision_step(accumulated_usage)
    assert step is not None
    assert step.exit_type == "undecided"


def test_crux_directive_followed_by_falsification_transitions_to_bounded_decision():
    """ibl-eacad98b3b83 (A4): crux directive initializing undecided step transitions to bounded decision on falsification."""
    from ouroboros.loop_nudges import (
        get_evolution_decision_step,
        _maybe_inject_evolution_crux_directive,
        _maybe_inject_evolution_deadline,
    )

    accumulated_usage = {}
    messages = []
    # Round 1 crux directive initializes undecided step
    _maybe_inject_evolution_crux_directive(1, messages, accumulated_usage, task_type="evolution")
    assert get_evolution_decision_step(accumulated_usage).exit_type == "undecided"

    # Objective is falsified in later rounds
    accumulated_usage["falsified_objective"] = True
    accumulated_usage["falsification_evidence"] = "API already removed in 7.4.16"
    accumulated_usage["residual_owed"] = True

    llm_trace = {"tool_calls": [{"tool": "read_file", "round_id": "exec_abc:round:1"}]}
    fired = _maybe_inject_evolution_deadline(10, messages, accumulated_usage, llm_trace=llm_trace, task_type="evolution")
    assert fired is True
    step = get_evolution_decision_step(accumulated_usage)
    assert step is not None
    assert step.falsified is True
    assert step.residual_owed is True
    assert step.exit_type == "residual_pin"
    text = messages[-1]["content"]
    assert "[BOUNDED DECISION DEADLINE" in text
    assert "LAND THE RESIDUAL PIN" in text



