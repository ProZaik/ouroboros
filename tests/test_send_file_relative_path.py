"""Regression: send_file resolves a relative path against the write_file landing root.

Incident (task 79c31b14): a deliverable written with
``write_file(root="user_files", path="<name>")`` was not sendable with that same
relative path — ``send_file`` resolved it against the process cwd and reported
"File not found", recovered only by passing an absolute Deliverables path.
"""
import types

from ouroboros.tools.core_artifacts import _send_file


def _make_ctx(chat_id=123, drive_root=None):
    return types.SimpleNamespace(
        current_chat_id=chat_id,
        pending_events=[],
        drive_root=drive_root,
        task_id="t-send-relative",
        task_metadata={},
    )


def test_relative_deliverable_is_sendable_without_absolute_retry(tmp_path, monkeypatch):
    from ouroboros.tool_access_user_files import resolve_user_file_path

    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = _make_ctx(drive_root=tmp_path / "drive")

    # Land the file through the same resolver write_file uses for user_files,
    # then send it back with the identical relative name.
    landing = resolve_user_file_path(ctx, "relative_deliverable.md")
    landing.parent.mkdir(parents=True, exist_ok=True)
    landing.write_text("hello", encoding="utf-8")

    result = _send_file(ctx, file_path="relative_deliverable.md")

    assert "OK" in result, result
    assert ctx.pending_events, "no send event emitted"
    assert ctx.pending_events[0]["filename"] == "relative_deliverable.md"
