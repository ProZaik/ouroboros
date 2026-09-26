"""Native read receipts carry exact delivered ranges without inventing coverage."""

import hashlib
import json

import pytest

from ouroboros.review_execution import ReviewAssignment, ReviewRouteKind
from ouroboros.review_native_episode import NativeToolRoundReviewExecutor
from ouroboros.review_substrate import ReviewRequest, ReviewSlot
from ouroboros.tools.core_file_tools import _read_file
from ouroboros.tools.registry import ToolContext


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _executor(root):
    request = ReviewRequest(surface="multi_model_review", goal="read evidence", session_root=str(root),
                            policy={"native_data_root": str(root / "data")})
    slot = ReviewSlot(slot_id="reader", model="openai/fake-reviewer", route=ReviewRouteKind.API_CHAT)
    return NativeToolRoundReviewExecutor(ReviewAssignment(request=request, slot=slot, call_id="extent"))


def _read(root, raw, **kwargs):
    (root / "source.md").write_bytes(raw)
    ctx = ToolContext(repo_dir=root, drive_root=root / "data")
    full = _read_file(ctx, "source.md", root="system_repo", **kwargs)
    executor = _executor(root)
    executor._inspection_ctx = ctx
    return executor, ctx, full


def test_partial_long_line_receipts_cover_only_the_delivered_normalized_source(tmp_path):
    raw = ("before\r\n" + "αβγ" * 1000 + "\r\nafter\r").encode()
    normalized = raw.decode().replace("\r\n", "\n").replace("\r", "\n")
    executor, ctx, full = _read(tmp_path, raw, start_line=2, max_lines=1, start_char=7)
    view = dict(ctx.last_read_view)
    first = executor._read_extent(full, view["body_start"] + 137)
    assert first["source_revision"] == _sha(raw)
    assert first["source_bytes"] == len(raw)
    assert first["complete_sha256"] == _sha(normalized.encode())
    assert first["complete_chars"] == len(normalized)
    assert first["range_basis"] == "unicode_text_universal_newlines"
    assert first["source_masked"] is False
    assert (first["source_start_char"], first["source_end_char"]) == (14, 151)
    assert first["text_chars"] == 137
    assert first["text_sha256"] == _sha(normalized[14:151].encode())
    assert first["end_line"] < first["start_line"]  # neither chunk delivered a complete line
    second_full = _read_file(ctx, "source.md", root="system_repo", start_line=2, max_lines=1, start_char=144)
    second = executor._read_extent(second_full, ctx.last_read_view["body_start"] + 137)
    assert second["source_start_char"] == first["source_end_char"]
    assert second["source_end_char"] == 288
    assert second["source_revision"] == first["source_revision"]
    assert second["text_sha256"] == _sha(normalized[151:288].encode())
    assert second["end_line"] < second["start_line"]


def test_exact_extent_excludes_headers_trailing_notes_and_unshown_body(tmp_path):
    executor, ctx, full = _read(tmp_path, "α first\nsecond\n".encode())
    view = ctx.last_read_view
    for shown in (0, view["body_start"] - 1, view["body_start"]):
        extent = executor._read_extent(full, shown)
        assert extent["source_start_char"] == extent["source_end_char"] == 0
        assert extent["text_chars"] == 0 and extent["text_sha256"] == _sha(b"")
        assert extent["eof"] is False
    with_note = full + "\nHOST NOTE: unrelated trailing text"
    extent = executor._read_extent(with_note, len(with_note))
    assert extent["source_end_char"] == extent["complete_chars"] == len("α first\nsecond\n")
    assert extent["text_sha256"] == _sha("α first\nsecond\n".encode())
    assert extent["text_chars"] < len(with_note)


def test_extent_keeps_revision_from_the_open_that_delivered_the_body(tmp_path):
    executor, ctx, full = _read(tmp_path, b"original\r\n")
    (tmp_path / "source.md").write_bytes(b"replacement\n")
    first = executor._read_extent(full, len(full))
    assert first["source_revision"] == _sha(b"original\r\n")
    assert first["text_sha256"] == _sha(b"original\n")
    new_full = _read_file(ctx, "source.md", root="system_repo")
    second = executor._read_extent(new_full, len(new_full))
    assert second["source_revision"] == _sha(b"replacement\n")
    assert second["source_revision"] != first["source_revision"]


@pytest.mark.parametrize("field", [
    "source_revision", "source_bytes", "complete_sha256", "complete_chars",
    "source_start_char", "source_end_char", "body_chars", "source_masked", "range_basis",
])
def test_missing_source_fact_retains_line_evidence_without_exact_proof(tmp_path, field):
    executor, ctx, full = _read(tmp_path, b"original\n")
    ctx.last_read_view.pop(field)
    extent = executor._read_extent(full, len(full))
    assert extent["start_line"] == extent["end_line"] == 1
    assert extent["eof"] is True
    assert not {"source_revision", "source_start_char", "source_end_char", "text_sha256"} & extent.keys()


@pytest.mark.parametrize("changed", [
    {"source_revision": "wrong"}, {"complete_sha256": "z" * 64},
    {"source_bytes": "9"}, {"complete_chars": -1}, {"source_start_char": True},
    {"source_start_char": 10}, {"source_end_char": 100}, {"body_chars": 100},
    {"body_start": True}, {"range_basis": "raw_bytes"}, {"source_masked": True},
])
def test_invalid_source_fact_never_mints_exact_range(tmp_path, changed):
    executor, ctx, full = _read(tmp_path, b"original\n")
    ctx.last_read_view.update(changed)
    extent = executor._read_extent(full, len(full))
    assert not {"source_revision", "source_start_char", "source_end_char", "text_sha256"} & extent.keys()


def test_masked_reader_body_does_not_prove_original_source_was_delivered(tmp_path):
    raw = b"safe preface\n-----BEGIN PRIVATE KEY-----\nmade-up-key-body\n-----END PRIVATE KEY-----\n"
    (tmp_path / "source.md").write_bytes(raw)
    ctx = ToolContext(repo_dir=tmp_path, drive_root=tmp_path / "data",
                      task_constraint={"mode": "local_readonly_subagent"})
    full = _read_file(ctx, "source.md", root="system_repo")
    assert ctx.last_read_view["source_masked"] is True
    assert "made-up-key-body" not in full
    executor = _executor(tmp_path)
    executor._inspection_ctx = ctx
    extent = executor._read_extent(full, len(full))
    assert "source_start_char" not in extent and "source_end_char" not in extent


def test_result_fitting_receipt_matches_exact_text_returned_to_the_reviewer(tmp_path):
    raw = ('α\\"\t' * 2000 + "\n").encode()
    (tmp_path / "source.md").write_bytes(raw)
    executor = _executor(tmp_path)
    registry, _schemas = executor._inspection_registry(str(tmp_path), tmp_path / "data")
    message = executor._execute_inspection_call(registry, {
        "id": "read-1", "function": {"name": "read_file", "arguments": json.dumps({"path": "source.md"})},
    }, {}, round_idx=1, room=1500)
    receipt = executor._tool_receipts[0]
    body_start = executor._inspection_ctx.last_read_view["body_start"]
    delivered = message["content"][body_start:body_start + receipt["text_chars"]]
    assert 0 < receipt["text_chars"] < len(raw.decode())
    assert receipt["source_end_char"] == receipt["text_chars"]
    assert receipt["text_sha256"] == _sha(delivered.encode())
    assert delivered == raw.decode()[:receipt["text_chars"]]
    assert message["content"][body_start + receipt["text_chars"]:].startswith("\n⚠️ RESULT TRUNCATED:")
    assert len(json.dumps(message, ensure_ascii=False)) + 2 <= 1500
    assert receipt["delivered"] is False
    assert receipt["stale"] is True
    assert receipt["source_gap"] == "tool_result_truncated"


def test_exact_source_identity_keeps_the_complete_opened_path(tmp_path):
    relative = "/".join(["subdirectory" * 5] * 6 + ["source.md"])
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_bytes(b"source\n")
    ctx = ToolContext(repo_dir=tmp_path, drive_root=tmp_path / "data")
    full = _read_file(ctx, relative, root="system_repo")
    executor = _executor(tmp_path)
    executor._inspection_ctx = ctx
    extent = executor._read_extent(full, len(full))
    assert len(relative) > 300
    assert extent["opened_path"] == relative
    assert extent["source_revision"] == _sha(b"source\n")


def test_compaction_invalidates_unpinned_read_receipts(tmp_path):
    (tmp_path / "a.txt").write_text("file A content\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("file B content\n", encoding="utf-8")
    executor = _executor(tmp_path)
    registry, schemas = executor._inspection_registry(str(tmp_path), tmp_path / "data")

    # Read a.txt in round 1
    m1 = executor._execute_inspection_call(registry, {
        "id": "call-a", "function": {"name": "read_file", "arguments": json.dumps({"path": "a.txt"})},
    }, {}, round_idx=1, room=50000)
    # Read b.txt in round 2
    m2 = executor._execute_inspection_call(registry, {
        "id": "call-b", "function": {"name": "read_file", "arguments": json.dumps({"path": "b.txt"})},
    }, {}, round_idx=2, room=50000)

    executor._observe_sent_view([], schemas)
    assert executor._tool_receipts[0]["delivered"] is True
    assert executor._tool_receipts[1]["delivered"] is True

    messages = [
        {"role": "user", "content": "review start"},
        {"role": "assistant", "content": "call-a", "tool_calls": [{"id": "call-a", "function": {"name": "read_file", "arguments": "{}"}}]},
        m1,
        {"role": "assistant", "content": "call-b", "tool_calls": [{"id": "call-b", "function": {"name": "read_file", "arguments": "{}"}}]},
        m2,
    ]
    executor._observe_sent_view(messages, schemas)

    from ouroboros.context_compaction import _atomic_units, context_reclaim_transcript_sha256
    units = _atomic_units(messages)
    assert len(units) == 2
    unit_a_id = units[0].unit_id
    unit_b_id = units[1].unit_id

    (tmp_path / "data").mkdir(exist_ok=True)

    rev = context_reclaim_transcript_sha256(messages)
    # Pin unit_a only
    executor._inspection_ctx._pinned_unit_ids = (unit_a_id,)
    executor._inspection_ctx._pending_compaction = {
        "observed": {"messages": messages, "tool_schemas": schemas, "revision": rev},
        "working_note": "only keeping pinned a",
        "expected_view_revision": rev,
        "keep_unit_ids": (unit_a_id,),
        "restore_unit_refs": (),
        "schema_names": None,
    }

    executor._transcript_bound = 500_000
    # Simulate applied compaction
    applied = executor._apply_working_view(messages, schemas, round_idx=3)
    assert applied is True
    assert executor._inspection_ctx._read_coverage_stale is True

    # Unit A receipt was pinned/retained: not invalidated
    assert executor._tool_receipts[0]["delivered"] is True
    assert not executor._tool_receipts[0].get("stale")

    # Unit B receipt was not retained or pinned: invalidated!
    assert executor._tool_receipts[1]["delivered"] is False
    assert executor._tool_receipts[1]["stale"] is True
    assert executor._tool_receipts[1]["source_gap"] == "compaction_invalidated"

