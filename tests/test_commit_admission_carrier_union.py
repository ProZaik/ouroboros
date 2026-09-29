"""Regression pin: release-carrier union in the reviewed-commit path.

Cycle #105 / backlog ibl-3335e3ff4420.

`auto_sync_release_metadata_if_needed` used to return ONLY the carriers that
`sync_release_metadata` had just rewritten. A carrier that was already coherent
on disk but modified against HEAD (for example a README whose badge already
matches VERSION because it was edited in an earlier step) was therefore never
surfaced, and `_stage_candidate_for_review`'s union
(`paths = sorted(set(paths) | set(synced))`) could not pick it up. A caller who
passed an explicit `paths` list naming only VERSION silently landed a commit
with the other carriers excluded -- a BIBLE P9 desync in the committed tree.

The fix unions every required carrier modified against HEAD
(`changed_worktree_paths(repo_dir) & CARRIER_SPAN_PATHS`) into the returned set
whenever VERSION is in scope, so the existing staging union stages them.

These tests pin the three branches of that contract:
  * a modified-but-coherent carrier is returned even when sync rewrote nothing;
  * sync-rewritten carriers are still returned;
  * with VERSION out of scope the function is a no-op.
"""

from __future__ import annotations

import types

import pytest

from ouroboros import commit_admission
from ouroboros.tools import release_sync


def _ctx() -> types.SimpleNamespace:
    return types.SimpleNamespace(task_id="pin-carrier-union")


def _isolate(monkeypatch, repo, *, worktree_paths, synced):
    """Point the two collaborators at fixed answers and mute side effects."""
    monkeypatch.setattr(
        commit_admission, "changed_worktree_paths", lambda _repo, paths=None: list(worktree_paths)
    )
    monkeypatch.setattr(release_sync, "sync_release_metadata", lambda _repo: list(synced))
    appended: list = []
    monkeypatch.setattr(
        commit_admission, "append_jsonl", lambda path, row: appended.append((str(path), row))
    )
    monkeypatch.setattr(commit_admission.subprocess, "run", lambda *a, **k: None)
    return appended


def test_modified_but_coherent_carrier_is_returned_when_sync_rewrites_nothing(
    tmp_path, monkeypatch
):
    """The exact residual: README.md modified vs HEAD, coherent on disk, sync rewrites []."""
    appended = _isolate(
        monkeypatch,
        tmp_path,
        worktree_paths=["VERSION", "README.md", "ouroboros/loop_nudges.py"],
        synced=[],
    )

    staged = commit_admission.auto_sync_release_metadata_if_needed(
        _ctx(), tmp_path, tmp_path, ["VERSION"]
    )

    # README.md is a required carrier and is modified vs HEAD: it must be staged.
    assert "README.md" in staged
    # VERSION is a carrier too and is in scope, so it is returned as well.
    assert "VERSION" in staged
    # A source file that is not a release carrier is never added by this helper.
    assert "ouroboros/loop_nudges.py" not in staged
    # The union is recorded durably with the staged set it actually used.
    assert appended, "auto-sync must append a release_metadata_auto_synced row"
    _path, row = appended[0]
    assert row["type"] == "release_metadata_auto_synced"
    assert "README.md" in row["changed_files"]


def test_sync_rewritten_carriers_are_still_returned(tmp_path, monkeypatch):
    """The pre-existing behavior must survive: carriers sync rewrites come back."""
    _isolate(
        monkeypatch,
        tmp_path,
        worktree_paths=["VERSION"],
        synced=["web/package.json", "web/modules/api_types.js"],
    )

    staged = commit_admission.auto_sync_release_metadata_if_needed(
        _ctx(), tmp_path, tmp_path, ["VERSION"]
    )

    assert "web/package.json" in staged
    assert "web/modules/api_types.js" in staged
    assert "VERSION" in staged


def test_version_out_of_scope_is_a_noop(tmp_path, monkeypatch):
    """Without VERSION in caller paths or worktree changes this helper does nothing."""
    _isolate(
        monkeypatch,
        tmp_path,
        worktree_paths=["docs/ARCHITECTURE.md"],
        synced=["README.md"],
    )

    staged = commit_admission.auto_sync_release_metadata_if_needed(
        _ctx(), tmp_path, tmp_path, ["ouroboros/loop_nudges.py"]
    )

    assert staged == []


def test_carrier_span_paths_is_the_union_authority(tmp_path, monkeypatch):
    """README.md and VERSION are the carrier names this contract depends on."""
    assert "README.md" in release_sync.CARRIER_SPAN_PATHS
    assert "VERSION" in release_sync.CARRIER_SPAN_PATHS


def test_stage_candidate_for_review_unions_synced_release_carriers(tmp_path, monkeypatch):
    """Fulfills ibl-206cfe1a121f and ibl-a345da4da977.

    Verifies that _stage_candidate_for_review exercises the real consumer seam:
    paths = sorted(set(paths) | set(synced)), passing the united paths to `git add`.
    Also asserts that the fake run_cmd returns string (not SimpleNamespace) so that
    status.strip() works as required by real consumer.
    """
    import time
    from ouroboros.tools import git_review_cycle

    ctx = types.SimpleNamespace(
        task_id="pin-consumer-union",
        repo_dir=str(tmp_path),
        drive_root=str(tmp_path),
        _review_resume_pending=False,
    )

    monkeypatch.setattr(
        "ouroboros.commit_admission.auto_sync_release_metadata_if_needed",
        lambda _ctx, _repo, _drive, _paths: ["README.md"],
    )

    executed_cmds = []

    class FakeGit:
        def safe_relpath(self, path):
            return str(path)

        def run_cmd(self, cmd, cwd=None):
            executed_cmds.append(cmd)
            if "status" in cmd:
                return "M  VERSION\nM  README.md\n"
            if "--name-status" in cmd:
                return "M\tVERSION\nM\tREADME.md\n"
            return ""

        def paths_from_name_status(self, raw):
            return ["README.md", "VERSION"]

    monkeypatch.setattr(git_review_cycle, "_git", lambda: FakeGit())

    classification, advisory, error = git_review_cycle._stage_candidate_for_review(
        ctx,
        commit_message="test union",
        commit_start=time.time(),
        paths=["VERSION"],
        came_from_detached_checkout=False,
    )

    assert error is None
    assert classification == ["README.md", "VERSION"]
    assert advisory == ["README.md", "VERSION"]

    add_calls = [cmd for cmd in executed_cmds if cmd and cmd[0] == "git" and cmd[1] == "add"]
    assert add_calls, "Expected at least one git add call"
    added_args = add_calls[0][2:]
    assert "README.md" in added_args
    assert "VERSION" in added_args
    assert added_args == ["README.md", "VERSION"]

