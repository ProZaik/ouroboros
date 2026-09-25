"""Tests for symbiotic evolution mode and backlog segregation.

Verifies:
1. Backlog candidate classification (system vs project repo).
2. Project improvement backlog updating and scoping.
3. Filtering in _run_global_backlog_promotion_only to prevent cross-repo contamination.
4. Preflight detection of external project objectives in self-evolution.
5. Symbiotic mode configuration and consciousness wake message injection.
"""

from __future__ import annotations

import json
import pathlib
from types import SimpleNamespace

import pytest

from ouroboros.backlog_classifier import is_system_improvement_candidate
import ouroboros.config as cfg
from ouroboros.post_task_synthesis import _update_project_improvement_backlog
import ouroboros.agent_task_pipeline as pipeline
from supervisor.evolution_lifecycle import _evolution_target_preflight
import ouroboros.consciousness_wake as wake


def test_classifier_identifies_project_artifacts_as_non_system():
    # runner.py in stand-appsec-pipeline (the root cause of cycle #70)
    candidate_runner = {
        "summary": "runner.py simulation gate and its test contradict each other after 569b7b5",
        "evidence": "tests/test_dynamic_coordinator.py::test_stand_runner_simulation_telemetry sets simulation_mode=True",
        "category": "correctness",
        "source": "post-task review",
    }
    assert is_system_improvement_candidate(candidate_runner, {"project_id": "stand-appsec-pipeline"}) is False
    assert is_system_improvement_candidate(candidate_runner) is False

    # Frida/APK/SAST/BoringSSL project items
    candidate_appsec = {
        "summary": "APK decompilation unpacker failed in stand48",
        "evidence": "boringssl hook error in jadx pass",
        "category": "tooling",
    }
    assert is_system_improvement_candidate(candidate_appsec, {"project_id": "stand-appsec-pipeline"}) is False


def test_classifier_identifies_ouroboros_system_items_as_system():
    candidate_tool = {
        "summary": "route_to_project predecessor check returned TOOL_ARG_ERROR",
        "evidence": "route_to_project failed with predecessor_task_id required",
        "category": "tool_ergonomics",
    }
    assert is_system_improvement_candidate(candidate_tool, {"project_id": "stand-appsec-pipeline"}) is True

    candidate_friction = {
        "summary": "Agent tool friction around edit_text anchor mismatch",
        "category": "process",
    }
    assert is_system_improvement_candidate(candidate_friction, {"project_id": "stand-appsec-pipeline"}) is True


def test_classifier_explicit_scope_overrides():
    assert is_system_improvement_candidate({"summary": "anything", "scope": "system"}) is True
    assert is_system_improvement_candidate({"summary": "anything", "scope": "project"}) is False


def test_update_project_improvement_backlog_writes_to_project_shelf(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    env = SimpleNamespace(drive_root=tmp_path, budget_drive_root=str(tmp_path))

    reflection = {
        "backlog_candidates": [
            {
                "summary": "runner.py simulation gate fix needed",
                "category": "correctness",
                "source": "test_failure",
            },
            {
                "summary": "run_command timeout needs adjustment",
                "category": "tooling",
                "source": "system",
            },
        ],
    }

    added = _update_project_improvement_backlog(env, reflection, project_id="stand-appsec-pipeline")
    # Only the project candidate should be added to the project backlog
    assert added == 1

    project_backlog_path = tmp_path / "projects" / "stand-appsec-pipeline" / "knowledge" / "improvement-backlog.md"
    assert project_backlog_path.exists()
    content = project_backlog_path.read_text(encoding="utf-8")
    assert "runner.py simulation gate fix needed" in content
    assert "run_command timeout needs adjustment" not in content


def test_run_global_backlog_promotion_only_filters_out_project_candidates(tmp_path, monkeypatch):
    import ouroboros.post_task_evolution as post_task_evolution

    promoted_tasks = []
    monkeypatch.setattr(
        post_task_evolution,
        "maybe_promote",
        lambda _env, task, entry, _llm: promoted_tasks.append((task, entry)),
    )
    env = SimpleNamespace(drive_root=tmp_path, drive_path=lambda rel: tmp_path / rel)

    # Reflection with only project defect
    project_reflection = {
        "backlog_candidates": [
            {
                "summary": "runner.py simulation gate contradiction in stand-appsec-pipeline",
                "evidence": "STAND_SIMULATION flag not set",
            }
        ]
    }
    task = {"id": "task-test", "project_id": "stand-appsec-pipeline"}
    pipeline._run_global_backlog_promotion_only(env, task, project_reflection, object())

    # Should not promote anything or write to global backlog
    assert len(promoted_tasks) == 0
    global_backlog = tmp_path / "memory" / "knowledge" / "improvement-backlog.md"
    assert not global_backlog.exists()

    # Now reflection with a system improvement
    system_reflection = {
        "backlog_candidates": [
            {
                "summary": "Improve route_to_project error message for live predecessor",
                "category": "tool_ergonomics",
            }
        ]
    }
    pipeline._run_global_backlog_promotion_only(env, task, system_reflection, object())
    assert len(promoted_tasks) == 1
    assert global_backlog.exists()
    assert "route_to_project" in global_backlog.read_text(encoding="utf-8")


def test_evolution_target_preflight_guards_against_external_project_objectives():
    objective = "Reconcile the runner.py simulation gate and its test after commit 569b7b5"
    obj_out, steer_out, note = _evolution_target_preflight(objective, "")

    assert "Objective targets an external project repo" in note
    assert "[PREFLIGHT: Objective targets an external project repo" in obj_out


def test_symbiotic_mode_config_and_wake_message(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "runtime_setting", lambda key, default=None: {
        "OUROBOROS_SYMBIOTIC_MODE": "true",
        "OUROBOROS_SYMBIOTIC_TARGET_PROJECT": "stand-appsec-pipeline",
        "OUROBOROS_SYMBIOTIC_CADENCE": "active",
    }.get(key, default))

    assert cfg.get_symbiotic_mode_enabled() is True
    assert cfg.get_symbiotic_target_project() == "stand-appsec-pipeline"
    assert cfg.get_symbiotic_cadence() == "active"

    repo = tmp_path / "repo"
    (repo / "prompts").mkdir(parents=True)
    (repo / "prompts" / "CONSCIOUSNESS.md").write_text("Hello {reason}. Wake: {events}", encoding="utf-8")

    text = wake.render_wake_message(
        tmp_path, repo, reason="heartbeat", last_wake_at=0.0, since=100.0, now=200.0,
        level="act", disabled_tools=[], spent_usd=0.0, daily_usd=20.0,
        running=0, max_tasks=2, interval=300,
    )

    assert "## Symbiotic Evolution Mode: Target Project" in text
    assert "- target_project: stand-appsec-pipeline" in text
    assert "Autonomous Principal AppSec / Systems Engineer" in text
