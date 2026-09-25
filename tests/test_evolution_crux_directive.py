"""Focused tests for the round-1 [CRUX-FIRST] evolution nudge (cycle #69).

The nudge is the P5-compliant realization of ibl-934c652d5e18: the host states
the crux-first policy, the LLM owns the search term. The sister half of that
objective — detecting a final answer that narrates an intended search — is a
prose classifier and is deliberately not implemented.
"""
from ouroboros.loop_nudges import _maybe_inject_evolution_crux_directive


def test_crux_directive_injected_at_first_round_for_evolution():
    messages = []
    accumulated_usage = {}
    fired = _maybe_inject_evolution_crux_directive(
        1, messages, accumulated_usage, task_type="evolution",
    )
    assert fired is True
    assert len(messages) == 1
    content = messages[0]["content"]
    assert "[CRUX-FIRST]" in content
    assert "FIRST tool call" in content
    assert accumulated_usage.get("_last_evolution_crux_directive_round") == 1


def test_crux_directive_not_injected_for_non_evolution():
    messages = []
    accumulated_usage = {}
    fired = _maybe_inject_evolution_crux_directive(
        1, messages, accumulated_usage, task_type="task",
    )
    assert fired is False
    assert messages == []
    assert "_last_evolution_crux_directive_round" not in accumulated_usage


def test_crux_directive_not_injected_after_first_round():
    messages = []
    accumulated_usage = {}
    fired = _maybe_inject_evolution_crux_directive(
        2, messages, accumulated_usage, task_type="evolution",
    )
    assert fired is False
    assert messages == []
    assert "_last_evolution_crux_directive_round" not in accumulated_usage


def test_crux_directive_latch_prevents_second_injection():
    messages = []
    accumulated_usage = {}
    first = _maybe_inject_evolution_crux_directive(
        1, messages, accumulated_usage, task_type="evolution",
    )
    second = _maybe_inject_evolution_crux_directive(
        1, messages, accumulated_usage, task_type="evolution",
    )
    assert first is True
    assert second is False
    assert len(messages) == 1


def test_crux_directive_states_policy_not_a_host_rejection_path():
    """The directive must state the policy for the LLM, not promise that the
    host will reject a prose claim of intent (the P5-falsified Half B)."""
    messages = []
    _maybe_inject_evolution_crux_directive(
        1, messages, {}, task_type="evolution",
    )
    content = messages[0]["content"]
    assert "Do not end a cycle with a final answer that narrates an intended" in content
