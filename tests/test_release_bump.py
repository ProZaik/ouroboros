"""Tests for atomic release bump wiring (scripts/release_bump.py and release_sync.bump_version)."""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

from ouroboros.tools.release_sync import (
    bump_version,
    check_history_limit,
    check_worktree_version_sync,
)
from tests.test_release_sync import _make_repo


def test_bump_version_updates_version_and_syncs_carriers(tmp_path):
    repo = _make_repo(tmp_path, version="4.99.1")

    res = bump_version(repo, "4.99.2", "Feature release test", release_date="2026-09-28")
    assert res == 0

    assert (repo / "VERSION").read_text(encoding="utf-8").strip() == "4.99.2"

    desync = check_worktree_version_sync(str(repo))
    assert desync == "", f"Expected 0 desyncs across carriers, got: {desync}"

    readme = (repo / "README.md").read_text(encoding="utf-8")
    assert "| 4.99.2 | 2026-09-28 | Feature release test |" in readme
    assert check_history_limit(readme) == []


def test_bump_version_trims_history_and_rolls_off(tmp_path):
    repo = _make_repo(tmp_path, version="4.99.1")

    # Add 5 patch releases
    for patch in range(2, 7):
        res = bump_version(repo, f"4.99.{patch}", f"Patch {patch}")
        assert res == 0

    readme = (repo / "README.md").read_text(encoding="utf-8")
    limit_warnings = check_history_limit(readme)
    assert limit_warnings == [], f"History limit exceeded: {limit_warnings}"

    # Now bump to 4.99.7: exceeds MAX_PATCH (5), so oldest patch row rolls off
    res = bump_version(repo, "4.99.7", "Patch 7")
    assert res == 0

    readme_after = (repo / "README.md").read_text(encoding="utf-8")
    assert check_history_limit(readme_after) == []
    assert "| 4.99.7 |" in readme_after


def test_bump_version_rejects_invalid_version(tmp_path):
    repo = _make_repo(tmp_path, version="4.99.1")

    res = bump_version(repo, "not_a_version", "Invalid bump")
    assert res == 1
    assert (repo / "VERSION").read_text(encoding="utf-8").strip() == "4.99.1"


def test_release_bump_cli_invocation(tmp_path):
    repo = _make_repo(tmp_path, version="4.99.1")
    script = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "release_bump.py"

    proc = subprocess.run(
        [sys.executable, str(script), "4.99.2", "-d", "CLI invocation test", "--date", "2026-09-28", "--repo", str(repo)],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"CLI bump failed: {proc.stderr}\n{proc.stdout}"
    assert (repo / "VERSION").read_text(encoding="utf-8").strip() == "4.99.2"
    assert check_worktree_version_sync(str(repo)) == ""
