"""Evolution-loop decision tool: let the model declare in-loop that the current
evolution objective has been falsified, so the round-10 deadline branch in
``ouroboros.loop_nudges`` can transition to the strong residual-pin notice.

Without this surface, ``accumulated_usage["falsified_objective"]`` and
``["falsification_evidence"]`` are READ by the deadline branch but written
nowhere in production — the typed branch was unreachable (ibl-1eca01304e56).
This module supplies the missing writer.
"""

from __future__ import annotations

from typing import Any

from ouroboros.loop_nudges import record_evolution_falsification
from ouroboros.tools.registry import ToolEntry


def _evolution_decision(
    ctx: Any,
    falsified: bool,
    reason: str = "",
    residual_owed: bool = True,
    target: str = "",
) -> str:
    task_type = getattr(ctx, "current_task_type", None)
    if task_type != "evolution":
        return (
            "REFUSED: evolution_decision is only available to evolution tasks "
            f"(current task_type={task_type!r})."
        )
    accumulated_usage = getattr(ctx, "_accumulated_usage", None)
    if not isinstance(accumulated_usage, dict):
        return (
            "REFUSED: evolution_decision requires the loop's accumulated_usage "
            "state, which is absent on this context."
        )

    if not falsified:
        accumulated_usage.pop("falsified_objective", None)
        accumulated_usage.pop("falsification_evidence", None)
        return (
            "Recorded: objective NOT falsified; the residual-pin deadline branch "
            "will not fire."
        )

    step = record_evolution_falsification(
        accumulated_usage,
        reason=reason,
        residual_owed=residual_owed,
        target=target,
    )
    accumulated_usage["falsified_objective"] = True
    accumulated_usage["falsification_evidence"] = reason
    accumulated_usage["residual_owed"] = residual_owed
    if target:
        accumulated_usage["falsification_target"] = target

    return (
        f"Recorded: objective falsified; exit_type={step.exit_type}; "
        f"residual_owed={step.residual_owed}; target={target or '<none>'}."
    )


def get_tools():
    return [
        ToolEntry("evolution_decision", {
            "name": "evolution_decision",
            "description": (
                "Declare in-loop that the current evolution objective has been "
                "falsified. When falsified=True the round-10 deadline transitions "
                "to the strong residual-pin notice so the residual can be landed "
                "instead of falling through to a no-op. Evolution tasks only."
            ),
            "parameters": {"type": "object", "properties": {
                "falsified": {
                    "type": "boolean",
                    "description": "True when the objective's premise has been falsified.",
                },
                "reason": {
                    "type": "string",
                    "description": "Concrete evidence that falsified the objective.",
                },
                "residual_owed": {
                    "type": "boolean",
                    "default": True,
                    "description": "Whether a narrow residual still owes a landing.",
                },
                "target": {
                    "type": "string",
                    "description": "Optional residual target (symbol or path).",
                },
            }, "required": ["falsified"]},
        }, lambda ctx, falsified, reason="", residual_owed=True, target="": _evolution_decision(
            ctx, falsified, reason, residual_owed, target,
        ), timeout_sec=15),
    ]


__all__ = ["get_tools"]
