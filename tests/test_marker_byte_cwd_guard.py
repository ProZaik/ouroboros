"""Focused pin for backlog ibl-cbcd0ccb8e38: leaked marker bytes (U+FF5C family)
in path-like tool args must be sanitized BEFORE the shell-cwd guard resolves them.

Defect class (placement, not absence): `_resolved_shell_cwd`
(ouroboros/tools/registry_guards.py) read `args.get("cwd")` RAW and fed the
marker-bearing string into `resolve_shell_cwd`, which rejected it with
SHELL_CWD_BLOCKED. The generic sanitizer in ouroboros/tools/tool_resolution.py
runs later, so it never protected this guard.

Both branches are required:
  * negative control — the marker is cleaned and the guard no longer blocks;
  * positive control — a genuinely clean cwd is unchanged (the guard was not
    merely suppressed).
"""
from __future__ import annotations

import pathlib
from types import SimpleNamespace

import ouroboros.tools.registry as registry_module
import ouroboros.tools.registry_guards as registry_guards
from ouroboros.tools.tool_result import ToolResult

MARKER = "\uff5c"  # U+FF5C, the leaked DSML marker byte


def _receiver(tmp_path: pathlib.Path) -> SimpleNamespace:
    return SimpleNamespace(
        _ctx=SimpleNamespace(drive_root=tmp_path, repo_dir=tmp_path),
    )


def _install_resolver(monkeypatch, seen: list[str]) -> None:
    def fake_resolve(ctx, raw_cwd, operation="shell"):
        seen.append(raw_cwd)
        # Mimic the real resolver: a marker-bearing path is rejected.
        if MARKER in raw_cwd:
            raise ValueError("marker byte in cwd")
        return (pathlib.Path(raw_cwd), None, True)

    monkeypatch.setattr(registry_module, "resolve_shell_cwd", fake_resolve)
    monkeypatch.setattr(
        registry_module,
        "shell_cwd_block_message",
        lambda *_a, **_k: "\u26a0\ufe0f SHELL_CWD_BLOCKED: marker byte in cwd",
    )


def test_marker_bearing_cwd_is_sanitized_before_the_guard(tmp_path, monkeypatch):
    seen: list[str] = []
    _install_resolver(monkeypatch, seen)

    marker_cwd = f"{tmp_path}/base{MARKER}DSML{MARKER}parameter>"
    result = registry_guards._resolved_shell_cwd(
        _receiver(tmp_path), {"cwd": marker_cwd},
    )

    assert not isinstance(result, ToolResult), (
        f"guard blocked the sanitized cwd: {result!r}"
    )
    assert seen, "resolver was never reached"
    assert MARKER not in seen[-1], f"resolver saw the raw marker byte: {seen[-1]!r}"
    assert "parameter>" not in seen[-1], f"resolver saw the raw marker tail: {seen[-1]!r}"
    assert result == pathlib.Path(f"{tmp_path}/base")


def test_clean_cwd_is_unchanged_by_the_guard(tmp_path, monkeypatch):
    seen: list[str] = []
    _install_resolver(monkeypatch, seen)

    clean_cwd = f"{tmp_path}/clean"
    result = registry_guards._resolved_shell_cwd(
        _receiver(tmp_path), {"cwd": clean_cwd},
    )

    assert not isinstance(result, ToolResult), f"guard blocked a clean cwd: {result!r}"
    assert seen[-1] == clean_cwd
    assert result == pathlib.Path(clean_cwd)
