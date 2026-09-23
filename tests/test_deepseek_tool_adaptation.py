from __future__ import annotations

import json
from ouroboros.tools.registry_core import ToolRegistry
from ouroboros.tools.tool_resolution import _prepare_public_builtin_args, _TOOL_ARG_ALIASES
from ouroboros.reflection import _extract_trailing_json


def test_tool_arg_aliases_for_deepseek(tmp_path):
    registry = ToolRegistry(repo_dir=tmp_path, drive_root=tmp_path)

    # 1. run_command
    entry = registry._entries.get("run_command")
    assert entry is not None
    args = {"command": "ls -la /root", "timeout": 45}
    err = _prepare_public_builtin_args(entry, args)
    assert err == "", f"Expected success but got {err}"
    assert args.get("cmd") == "ls -la /root"
    assert args.get("timeout_sec") == 45
    assert "command" not in args
    assert "timeout" not in args

    # 2. run_script
    entry = registry._entries.get("run_script")
    assert entry is not None
    args = {"code": "print('hello from deepseek')"}
    err = _prepare_public_builtin_args(entry, args)
    assert err == "", f"Expected success but got {err}"
    assert args.get("script") == "print('hello from deepseek')"
    assert "code" not in args

    # 3. read_file
    entry = registry._entries.get("read_file")
    assert entry is not None
    args = {"file": "README.md"}
    err = _prepare_public_builtin_args(entry, args)
    assert err == "", f"Expected success but got {err}"
    assert args.get("path") == "README.md"
    assert "file" not in args

    # 4. write_file
    entry = registry._entries.get("write_file")
    assert entry is not None
    args = {"file": "test.txt", "file_content": "hello world"}
    err = _prepare_public_builtin_args(entry, args)
    assert err == "", f"Expected success but got {err}"
    assert args.get("path") == "test.txt"
    assert args.get("content") == "hello world"
    assert "file" not in args
    assert "file_content" not in args

    # 5. edit_text
    entry = registry._entries.get("edit_text")
    assert entry is not None
    args = {"file": "test.txt", "search": "foo", "replace": "bar"}
    err = _prepare_public_builtin_args(entry, args)
    assert err == "", f"Expected success but got {err}"
    assert args.get("path") == "test.txt"
    assert args.get("old_str") == "foo"
    assert args.get("new_str") == "bar"
    assert "search" not in args
    assert "replace" not in args


def test_reflection_json_repair_fallback():
    # Trailing MEMORY_ACTIONS_JSON with unescaped quotes in content
    text = (
        "Here is my reflection on the execution.\n\n"
        "MEMORY_ACTIONS_JSON: [\n"
        '  {"type": "pattern_write", "pattern_id": "test_pat", "title": "Test Title", "content": "Unescaped "nested" quotes in content without breaking"}\n'
        "]"
    )
    marker = "MEMORY_ACTIONS_JSON:"
    remainder, parsed = _extract_trailing_json(text, marker)
    assert parsed is not None
    assert isinstance(parsed, list)
    assert len(parsed) == 1
    assert parsed[0]["type"] == "pattern_write"
    assert "Unescaped" in parsed[0]["content"]
    assert "Here is my reflection" in remainder


def test_str_match_replace_nearest_context():
    from ouroboros.tools.core import _str_match_replace

    text = "line 1\nline 2 target\nline 3\nline 4\n"
    new_text, err = _str_match_replace(
        text,
        "line 2 target typo",
        "replacement",
        "demo.py",
        "STR_REPLACE_ERROR"
    )
    assert new_text is None
    assert "⚠️ STR_REPLACE_ERROR: old_str not found in demo.py." in err
    assert "Nearest candidate match near line 2:" in err
    assert "line 2 target" in err
