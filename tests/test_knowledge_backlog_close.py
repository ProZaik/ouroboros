"""Regression tests for knowledge_write targeted backlog close and project routing (ibl-a206d7c25663, ibl-dbdc1127ab00).

Asserts that:
1. knowledge_write(topic='improvement-backlog', mode='close', content='ibl-xxx') flips the item to status: done.
2. Project-scoped knowledge_write(topic='improvement-backlog', scope='project:...', mode='close', ...) closes items in the per-project backlog.
3. merge_backlog_text closes items carrying status: done without re-opening them.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from ouroboros.improvement_backlog import (
    append_backlog_items,
    load_backlog_items,
    merge_backlog_text,
)
from ouroboros.tools.knowledge import _knowledge_write


@pytest.fixture
def temp_drive():
    with tempfile.TemporaryDirectory() as td:
        drive_path = Path(td)
        yield drive_path


def test_merge_backlog_text_closes_status_done_items(temp_drive):
    # Seed an open item
    item = {
        "id": "ibl-test0001",
        "summary": "Sample open item",
        "category": "process",
        "source": "task",
        "status": "open",
    }
    append_backlog_items(temp_drive, [item])

    items = load_backlog_items(temp_drive)
    assert len(items) == 1
    assert items[0]["status"] == "open"

    # Merge an update marking it done
    update_text = """### ibl-test0001
- status: done
- summary: Sample open item
- closed_at: 2026-09-28T18:00:00+00:00
"""
    changed = merge_backlog_text(temp_drive, update_text)
    assert changed >= 1

    items_after = load_backlog_items(temp_drive)
    assert len(items_after) == 1
    assert items_after[0]["status"] == "done"
    assert items_after[0].get("closed_at") is not None


def test_knowledge_write_mode_close_global(temp_drive):
    item = {
        "id": "ibl-test0002",
        "summary": "Another open item",
        "category": "tooling",
        "source": "task",
        "status": "open",
    }
    append_backlog_items(temp_drive, [item])

    ctx = SimpleNamespace(
        drive_root=str(temp_drive),
        repo_dir=str(temp_drive),
        system_repo_dir=str(temp_drive),
        project_id="",
        task_id="task_close_test",
    )

    res = _knowledge_write(
        ctx,
        topic="improvement-backlog",
        content="Closed via review: ibl-test0002",
        mode="close",
    )
    assert "closed 1 item(s)" in res
    assert "ibl-test0002" in res

    items_after = load_backlog_items(temp_drive)
    assert len(items_after) == 1
    assert items_after[0]["status"] == "done"


def test_knowledge_write_mode_close_project_scoped(temp_drive):
    pid = "stand-appsec-pipeline"
    item = {
        "id": "ibl-test0003",
        "summary": "Project-scoped open item",
        "category": "tooling",
        "source": "task",
        "status": "open",
    }
    append_backlog_items(temp_drive, [item], project_id=pid)

    ctx = SimpleNamespace(
        drive_root=str(temp_drive),
        repo_dir=str(temp_drive),
        system_repo_dir=str(temp_drive),
        project_id="",
        task_id="task_close_project_test",
    )

    res = _knowledge_write(
        ctx,
        topic="improvement-backlog",
        scope=f"project:{pid}",
        content="Closed in commit 123456: ibl-test0003",
        mode="close",
    )
    assert "closed 1 item(s)" in res
    assert "project 'stand-appsec-pipeline'" in res
    assert "ibl-test0003" in res

    items_after = load_backlog_items(temp_drive, project_id=pid)
    assert len(items_after) == 1
    assert items_after[0]["status"] == "done"


def test_merge_backlog_text_closes_status_done_without_summary(temp_drive):
    """Pin: closing an existing item via merge_backlog_text works even if summary is omitted in the markdown snippet."""
    item = {
        "id": "ibl-test0004",
        "summary": "Item to close without summary",
        "category": "process",
        "source": "task",
        "status": "open",
    }
    append_backlog_items(temp_drive, [item])

    update_text = """### ibl-test0004
- status: done
"""
    changed = merge_backlog_text(temp_drive, update_text)
    assert changed >= 1

    items_after = load_backlog_items(temp_drive)
    assert len(items_after) == 1
    assert items_after[0]["status"] == "done"
    assert items_after[0]["summary"] == "Item to close without summary"


def test_knowledge_write_mode_close_global_in_project_room(temp_drive):
    """Pin: knowledge_write with mode='close' closes in the global backlog when no project scope is requested, even if ctx.project_id is set."""
    item = {
        "id": "ibl-test0005",
        "summary": "Global item to close from project room",
        "category": "tooling",
        "source": "task",
        "status": "open",
    }
    append_backlog_items(temp_drive, [item])

    ctx = SimpleNamespace(
        drive_root=str(temp_drive),
        repo_dir=str(temp_drive),
        system_repo_dir=str(temp_drive),
        project_id="stand-appsec-pipeline",
        task_id="task_close_global_from_room",
    )

    res = _knowledge_write(
        ctx,
        topic="improvement-backlog",
        content="Closed: ibl-test0005",
        mode="close",
    )
    assert "closed 1 item(s)" in res
    assert "global" in res
    assert "ibl-test0005" in res

    items_after = load_backlog_items(temp_drive)
    assert len(items_after) == 1
    assert items_after[0]["status"] == "done"

