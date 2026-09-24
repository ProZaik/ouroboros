"""Tests for DeepSeek Bridge telemetry ingestion and client-side transcript compaction."""

import copy
import pytest

from ouroboros.llm_stream import extract_bridge_telemetry_headers
from ouroboros.llm_attempt import _compact_transcript_for_fit, _fit_output_payload


def test_extract_bridge_telemetry_headers_complete():
    headers = {
        "X-Bridge-Truncated": "true",
        "X-Bridge-Prompt-Chars": "125000",
        "X-Bridge-Dropped-Chars": "4200",
        "X-Bridge-Thinking-Duration-Ms": "1850",
        "X-Bridge-Account-Id": "acc_01_primary",
    }
    telemetry = extract_bridge_telemetry_headers(headers)
    assert telemetry == {
        "truncated": True,
        "prompt_chars": 125000,
        "dropped_chars": 4200,
        "thinking_duration_ms": 1850,
        "account_id": "acc_01_primary",
    }


def test_extract_bridge_telemetry_headers_empty_or_malformed():
    assert extract_bridge_telemetry_headers(None) == {}
    assert extract_bridge_telemetry_headers({}) == {}
    headers = {
        "x-bridge-truncated": "false",
        "x-bridge-prompt-chars": "not_an_int",
    }
    telemetry = extract_bridge_telemetry_headers(headers)
    assert telemetry.get("truncated") is False
    assert "prompt_chars" not in telemetry


def test_compact_transcript_for_fit_preserves_head_and_tail():
    messages = [
        {"role": "system", "content": "You are Ouroboros. Maintain system integrity."},  # 0
        {"role": "user", "content": "Initial user task requirement."},                   # 1
        {"role": "assistant", "content": "A" * 600},                                     # 2 (foldable)
        {"role": "tool", "content": "B" * 1000},                                         # 3 (foldable)
        {"role": "assistant", "content": "Recent response 1"},                           # 4 (tail - protected)
        {"role": "user", "content": "Recent user turn 1"},                               # 5 (tail - protected)
        {"role": "assistant", "content": "Recent response 2"},                           # 6 (tail - protected)
        {"role": "tool", "content": "Recent tool result"},                               # 7 (tail - protected)
    ]
    compacted, dropped = _compact_transcript_for_fit(messages)
    assert dropped > 0
    # System and initial prompt untouched
    assert compacted[0]["content"] == "You are Ouroboros. Maintain system integrity."
    assert compacted[1]["content"] == "Initial user task requirement."
    # Protected tail untouched
    assert compacted[4]["content"] == "Recent response 1"
    assert compacted[5]["content"] == "Recent user turn 1"
    assert compacted[6]["content"] == "Recent response 2"
    assert compacted[7]["content"] == "Recent tool result"
    # Intermediate turns folded
    assert "... [Folded older assistant text" in compacted[2]["content"]
    assert "... [Folded older tool output" in compacted[3]["content"]


def test_compact_transcript_short_conversation_unchanged():
    messages = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "Short question"},
    ]
    compacted, dropped = _compact_transcript_for_fit(messages)
    assert compacted == messages
    assert dropped == 0


def test_compact_transcript_backlog_preserved_under_1m_chars():
    # A 100k character backlog note or large file must NOT be truncated by Pass 0
    backlog_text = "# Improvement Backlog\n" + ("- item: detail\n" * 4000)
    assert len(backlog_text) > 60_000
    messages = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "Read the backlog"},
        {"role": "tool", "content": backlog_text},
        {"role": "assistant", "content": "I see the backlog"},
        {"role": "user", "content": "What is next?"},
        {"role": "assistant", "content": "Thinking..."},
    ]
    compacted, dropped = _compact_transcript_for_fit(messages, capacity_tokens=500_000)
    # Tool output was NOT truncated by Pass 0 because it is under 1,000,000 characters
    assert compacted[2]["content"] == backlog_text


def test_compact_transcript_massive_tool_capped_at_250k_tokens():
    # A massive 1.2M char tool result (like a 4.8MB AST dump) must be capped to 1M chars (250k tokens)
    massive_tool = "H" * 600_000 + "MIDDLE" + "T" * 600_000  # 1.2M chars
    messages = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "Run massive tool"},
        {"role": "tool", "content": massive_tool},
        {"role": "assistant", "content": "Got result"},
        {"role": "user", "content": "Continue"},
        {"role": "assistant", "content": "Working..."},
    ]
    compacted, dropped = _compact_transcript_for_fit(messages, capacity_tokens=500_000)
    assert dropped == len(massive_tool) - 1_000_000
    assert "... [Truncated massive tool output" in compacted[2]["content"]
    assert compacted[2]["content"].startswith("H" * 500_000)
    assert compacted[2]["content"].endswith("T" * 500_000)
