"""Comprehensive stress and regression test suite for Ouroboros Boost improvements.

Covers:
1. Context window assertion (200k tokens) and context-fit pre-dispatch guard.
2. Platform layer lock concurrency and alive-PID stale lock recovery (deadlock prevention).
3. Loopback LLM probe reachability across multiple HTTP response codes and target types.
4. Release carrier synchronization including README.md Version History validation.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import pathlib
import re
import tempfile
import threading
import time
from unittest import mock

import pytest

from ouroboros import config, context_fit, loop_model_call, platform_layer, reviewer_window
from ouroboros.model_slots import MODEL_CONTEXT_WINDOWS_KEY, model_role_option
from ouroboros.tools.release_sync import version_carrier_desyncs, run_release_preflight


# ===========================================================================
# 1. CONTEXT FIT & 200K WINDOW STRESS TESTS
# ===========================================================================

class TestContextFit200kStress:
    """Stress-test the 200k token context window assertion and capacity guards."""

    def test_settings_200k_context_windows_resolved(self):
        """Verify that 200k context windows are resolved across configured model roles."""
        settings = {
            MODEL_CONTEXT_WINDOWS_KEY: json.dumps({
                "main": 200_000,
                "light": 200_000,
                "consciousness": 200_000,
                "deep_review": 200_000,
            })
        }
        for role in ("main", "light", "consciousness", "deep_review"):
            window = model_role_option(MODEL_CONTEXT_WINDOWS_KEY, role, settings=settings)
            assert window == 200_000, f"Expected 200k for {role}, got {window}"

    def test_context_fit_route_evidence_asserts_200k(self, monkeypatch, tmp_path):
        """Verify that context route evidence reflects the asserted 200k window."""
        settings = {
            "OUROBOROS_MODEL": "openai-compatible::deepseek-reasoner",
            "OPENAI_COMPATIBLE_BASE_URL": "http://127.0.0.1:8318/v1",
            MODEL_CONTEXT_WINDOWS_KEY: json.dumps({"main": 200_000}),
            "OUROBOROS_CONTEXT_MODE": "max",
        }
        monkeypatch.setattr(config, "runtime_settings", lambda: settings)

        task = {"id": "stress_task_001", "model_role": "main"}
        route, evidence = context_fit.resolve_context_fit_route(task, allow_fetch=False)
        assert evidence.window_tokens == 200_000
        assert evidence.status == "asserted"
        assert evidence.source == "user_setting"
        assert not evidence.stale

    def test_measure_main_fit_within_200k_capacity(self, tmp_path):
        """A prompt within 200k tokens must fit without capacity deficit."""
        plan = mock.MagicMock()
        plan.route_fp = "test_route_200k"
        plan.model = "deepseek-reasoner"
        plan.provider = "openai-compatible"
        plan.output_reserve_tokens = 16_384
        plan.window_tokens = 200_000
        plan.status = "asserted"
        plan.stale = False

        # Generate a medium-sized prompt (~50,000 tokens ~200k chars)
        messages = [
            {"role": "system", "content": "You are Ouroboros."},
            {"role": "user", "content": "A" * 150_000},
        ]
        disposition = context_fit.measure_main_fit(
            plan,
            messages,
            tools=[],
            drive_root=tmp_path,
            profile="owner_max",
            rendered_mode="max",
            round_id="test_round:1",
            automatic_pass_used=False,
        )
        assert disposition.predicted_capacity_miss is False
        assert disposition.measurement.capacity_total_tokens == 200_000
        assert disposition.measurement.capacity_deficit_tokens == 0
        assert disposition.action == "send"

    def test_measure_main_fit_exceeding_200k_triggers_capacity_miss(self, tmp_path):
        """A prompt exceeding 200k tokens must flag capacity deficit."""
        plan = mock.MagicMock()
        plan.route_fp = "test_route_200k"
        plan.model = "deepseek-reasoner"
        plan.provider = "openai-compatible"
        plan.output_reserve_tokens = 16_384
        plan.window_tokens = 200_000
        plan.status = "asserted"
        plan.stale = False

        # Generate a giant prompt (~220,000 tokens ~880k chars)
        messages = [
            {"role": "system", "content": "You are Ouroboros."},
            {"role": "user", "content": "B" * 880_000},
        ]
        disposition = context_fit.measure_main_fit(
            plan,
            messages,
            tools=[],
            drive_root=tmp_path,
            profile="owner_max",
            rendered_mode="max",
            round_id="test_round:2",
            automatic_pass_used=False,
        )
        assert disposition.predicted_capacity_miss is True
        assert disposition.measurement.capacity_deficit_tokens > 0
        assert disposition.action == "reclaim_once"

    def test_pre_dispatch_guard_reprojects_to_low(self):
        """Verify pre-dispatch guard in loop_model_call reprojects to low when predicted capacity miss."""
        mock_ctx = mock.MagicMock()
        mock_ctx.active_context_mode = "max"
        mock_ctx.round_idx = 1
        mock_ctx.task_id = "test_task_reproject"
        mock_ctx.messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}]
        mock_ctx.tool_schemas = []
        mock_ctx.tools._ctx.messages = mock_ctx.messages
        mock_ctx.tools._ctx.active_context_mode = "max"
        mock_ctx.context_fit_plan = mock.MagicMock()
        mock_ctx.context_fit_plan.reproject_transcript.return_value = [
            {"role": "system", "content": "compact_sys"},
            {"role": "user", "content": "usr"}
        ]

        # Call _reproject_actual_overflow_low
        with mock.patch("ouroboros.loop_model_call.invalidate_task_cache_splits"):
            with mock.patch("ouroboros.loop_model_call._loop") as mock_loop:
                loop_model_call._reproject_actual_overflow_low(mock_ctx)
                assert mock_ctx.active_context_mode == "low"
                assert mock_ctx.messages[0]["content"] == "compact_sys"
                assert mock_loop()._emit_checkpoint_event.called


# ===========================================================================
# 2. PLATFORM LAYER LOCK & CONCURRENCY STRESS TESTS
# ===========================================================================

class TestPlatformLockStress:
    """Stress test file locking, contention, and stale lock eviction."""

    def test_concurrent_lock_contention_no_deadlock(self, tmp_path):
        """Stress test 20 concurrent threads attempting to acquire and release a lock."""
        lock_file = tmp_path / "contention_test.lock"
        counter = {"acquired": 0, "failures": 0}
        lock = threading.Lock()

        def worker(worker_id: int):
            for _ in range(5):
                fd = platform_layer.acquire_exclusive_file_lock(
                    lock_file,
                    timeout_sec=2.0,
                    stale_sec=1.0,
                    owner_aware_stale=True,
                )
                if fd is not None:
                    with lock:
                        counter["acquired"] += 1
                    time.sleep(0.01)  # hold briefly
                    platform_layer.release_exclusive_file_lock(lock_file, fd)
                else:
                    with lock:
                        counter["failures"] += 1
                time.sleep(0.005)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(worker, i) for i in range(10)]
            concurrent.futures.wait(futures)

        assert counter["acquired"] > 0

    def test_alive_pid_stale_lock_recovered_after_timeout(self, tmp_path):
        """Verify that when owner PID is alive (current process), a lock older than stale_sec
        IS properly evicted rather than held in a permanent deadlock."""
        lock_file = tmp_path / "stale_alive.lock"

        # Manually create a lock with the CURRENT process PID, backdated by 5 seconds
        current_pid = os.getpid()
        lock_file.write_text(f"v1 0 {current_pid} 0\npid={current_pid}\n", encoding="utf-8")
        st_old = time.time() - 10.0
        os.utime(lock_file, (st_old, st_old))

        # Under the old buggy code:
        # stale was forced to False because current_pid is alive.
        # Under the fixed code:
        # age > stale_sec (10s > 2s) means stale=True, and lock is recovered!
        fd = platform_layer.acquire_exclusive_file_lock(
            lock_file,
            timeout_sec=2.0,
            stale_sec=2.0,
            owner_aware_stale=True,
        )
        assert fd is not None, "Failed to recover stale lock"
        platform_layer.release_exclusive_file_lock(lock_file, fd)


# ===========================================================================
# 3. LLM PROBE LOOPBACK REACHABILITY STRESS TESTS
# ===========================================================================

class TestLlmProbeLoopbackStress:
    """Stress test loopback reachability probes on port 8318 with varied HTTP responses."""

    def test_loopback_probes_various_http_statuses(self):
        """Verify handling of various upstream statuses (200, 501, 502, 503, 504)."""
        from ouroboros import llm_probe

        class _MockClient:
            def __init__(self, code: int):
                self.code = code
                self.calls = []

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def head(self, url: str):
                self.calls.append(url)
                resp = mock.MagicMock()
                resp.status_code = self.code
                return resp

        class _MockLLM:
            def __init__(self, base_url: str):
                self.base_url = base_url

            def _resolve_remote_target(self, model: str):
                return {"base_url": self.base_url}

            def _no_proxy_timeout(self, timeout):
                t = mock.MagicMock()
                t.connect = timeout
                return t

        llm = _MockLLM("http://127.0.0.1:8318/v1")

        # 1. 200 OK -> Reachable
        with mock.patch("httpx.Client", return_value=_MockClient(200)):
            res = llm_probe.upstream_transport_reachable(llm, "deepseek-reasoner", timeout=2.0)
            assert res.get("kind") == "upstream_http"
            assert res.get("status_code") == 200

        # 2. 501 Not Implemented (DeepSeek bridge HEAD response) -> Reachable on loopback
        with mock.patch("httpx.Client", return_value=_MockClient(501)):
            res = llm_probe.upstream_transport_reachable(llm, "deepseek-reasoner", timeout=2.0)
            assert res.get("kind") == "upstream_http"
            assert res.get("status_code") == 501

        # 3. Non-loopback 501 -> Not reachable
        non_loopback_llm = _MockLLM("https://api.deepseek.com/v1")
        with mock.patch("httpx.Client", return_value=_MockClient(501)):
            res = llm_probe.upstream_transport_reachable(non_loopback_llm, "deepseek-reasoner", timeout=2.0)
            assert res == {}

        # 4. Connection error -> Empty result (graceful handling, no uncaught exception)
        def raise_conn_err(*args, **kwargs):
            import httpx
            raise httpx.ConnectError("Connection refused")

        with mock.patch("httpx.Client", side_effect=raise_conn_err):
            res = llm_probe.upstream_transport_reachable(llm, "deepseek-reasoner", timeout=2.0)
            assert res == {}


# ===========================================================================
# 4. RELEASE CARRIER & VERSION HISTORY STRESS TESTS
# ===========================================================================

class TestReleaseCarrierStress:
    """Stress test release sync metadata and README.md Version History checks."""

    def test_desync_catches_missing_version_history(self):
        """When README.md has a Version History table, missing the current VERSION row must desync."""
        readme = (
            "# Ouroboros\n\n"
            "[![Version 7.4.11](https://img.shields.io/badge/version-7.4.11-green.svg)](VERSION)\n\n"
            "## Version History\n\n"
            "| Version | Date | Description |\n"
            "| 7.4.10 | 2026-09-23 | previous release |\n"
            "| 7.4.9 | 2026-09-22 | older release |\n"
        )
        desync = version_carrier_desyncs("7.4.11", readme_text=readme, detailed=True)
        assert any("Version History" in d for d in desync)
        assert "README.md Version History (expected row for | 7.4.11 |)" in desync

    def test_desync_passes_when_version_history_present(self):
        """When the Version History row is properly added, no desync is reported."""
        readme = (
            "# Ouroboros\n\n"
            "[![Version 7.4.11](https://img.shields.io/badge/version-7.4.11-green.svg)](VERSION)\n\n"
            "## Version History\n\n"
            "| Version | Date | Description |\n"
            "| 7.4.11 | 2026-09-23 | new boost release |\n"
            "| 7.4.10 | 2026-09-23 | previous release |\n"
        )
        desync = version_carrier_desyncs("7.4.11", readme_text=readme, detailed=True)
        assert not any("Version History" in d for d in desync)

    def test_run_release_preflight_warns_on_missing_changelog_row(self, tmp_path):
        """run_release_preflight must produce an advisory warning if README history row is missing."""
        (tmp_path / "VERSION").write_text("7.4.11\n", encoding="utf-8")
        (tmp_path / "README.md").write_text(
            "# Ouroboros\n\n"
            "[![Version 7.4.11](https://img.shields.io/badge/version-7.4.11-green.svg)](VERSION)\n\n"
            "## Version History\n\n"
            "| Version | Date | Description |\n"
            "| 7.4.10 | 2026-09-23 | previous release |\n",
            encoding="utf-8",
        )
        changed, warnings = run_release_preflight(str(tmp_path))
        assert any("Version History is missing a row for version 7.4.11" in w for w in warnings)
