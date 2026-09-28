"""Regression tests for baseline reconciliation and head_mismatch recovery in evolution mode."""

from __future__ import annotations

import pathlib
import subprocess
from types import SimpleNamespace

from ouroboros.tools.git_evolution import _evolution_commit_authority
from ouroboros.mutation_attribution import (
    capture_mutation_baseline,
    resolve_attributed_git_paths,
)
from ouroboros.task_results import STATUS_RUNNING, load_task_result, write_task_result


def _git(root: pathlib.Path, *args: str) -> str:
    res = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return res.stdout.strip()


def _make_git_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "tests@example.invalid")
    _git(repo, "config", "user.name", "Tests")
    (repo / "base.txt").write_text("initial\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "initial")
    return repo


def test_evolution_authority_reconciles_when_expected_sha_is_ancestor(tmp_path, monkeypatch):
    """When an external commit lands over the reviewed SHA before pre_tag_authority,
    if expected_sha is an ancestor of HEAD, it should reconcile instead of failing with head_mismatch."""
    repo = _make_git_repo(tmp_path)
    base_sha = _git(repo, "rev-parse", "HEAD")

    # Create the reviewed commit
    (repo / "feature.txt").write_text("feature\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "reviewed commit")
    reviewed_sha = _git(repo, "rev-parse", "HEAD")

    # Simulate an external commit landing over reviewed_sha
    (repo / "external.txt").write_text("external\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "external commit")
    new_head = _git(repo, "rev-parse", "HEAD")
    assert new_head != reviewed_sha

    ctx = SimpleNamespace(
        repo_dir=str(repo),
        task_id="task-123",
        task_metadata={
            "evolution_transaction": {
                "campaign_id": "camp-1",
                "transaction_id": "tx-1",
                "task_id": "task-123",
            }
        },
    )

    # Mock check_evolution_authority to simulate a valid claim with commit receipt
    from supervisor import evolution_lifecycle
    monkeypatch.setattr(
        evolution_lifecycle,
        "check_evolution_authority",
        lambda **kwargs: {"ok": True, "reason": ""},
    )

    claim, authority = _evolution_commit_authority(ctx, commit_sha=reviewed_sha, require_receipt=True)
    assert authority["ok"] is True
    assert authority.get("reason", "") != "head_mismatch"


def test_evolution_authority_refuses_when_head_diverged(tmp_path, monkeypatch):
    """When HEAD has truly diverged (expected_sha is not an ancestor), authority must refuse with head_mismatch."""
    repo = _make_git_repo(tmp_path)

    # Branch 1: reviewed commit
    _git(repo, "checkout", "-qb", "branch-a")
    (repo / "feature_a.txt").write_text("feature a\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "feature a")
    sha_a = _git(repo, "rev-parse", "HEAD")

    # Branch 2: external diverged commit
    _git(repo, "checkout", "-qb", "branch-b", "HEAD~1")
    (repo / "feature_b.txt").write_text("feature b\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "feature b")
    sha_b = _git(repo, "rev-parse", "HEAD")

    ctx = SimpleNamespace(
        repo_dir=str(repo),
        task_id="task-diverged",
        task_metadata={
            "evolution_transaction": {
                "campaign_id": "camp-1",
                "transaction_id": "tx-1",
                "task_id": "task-diverged",
            }
        },
    )

    from supervisor import evolution_lifecycle
    monkeypatch.setattr(
        evolution_lifecycle,
        "check_evolution_authority",
        lambda **kwargs: {"ok": True, "reason": ""},
    )

    claim, authority = _evolution_commit_authority(ctx, commit_sha=sha_a, require_receipt=True)
    assert authority["ok"] is False
    assert authority["reason"] == "head_mismatch"


def test_resolve_attributed_paths_reanchors_when_baseline_stale(tmp_path):
    """resolve_attributed_git_paths must heal baseline_stale via try_reanchor_stale_baseline
    when external commits did not touch the task's modified paths."""
    repo = _make_git_repo(tmp_path)
    data = tmp_path / "data"
    write_task_result(data, "task-heal", STATUS_RUNNING)

    capture_mutation_baseline(
        data,
        "task-heal",
        [{"surface_type": "system_repo", "host_root": str(repo)}],
    )

    # Task modifies its own file
    (repo / "task_work.py").write_text("print('hello')\n", encoding="utf-8")

    # Foreign commit lands on HEAD touching an unrelated file
    (repo / "unrelated_landing.md").write_text("# Documentation\n", encoding="utf-8")
    _git(repo, "add", "unrelated_landing.md")
    _git(repo, "commit", "-qm", "docs: external landing")

    selected, evidence, error = resolve_attributed_git_paths(data, "task-heal", repo, None)
    assert error == "", f"Expected successful re-anchoring, got error: {error}"
    assert selected == ["task_work.py"]
    assert "baseline_stale" not in (evidence.get("blockers") or [])
