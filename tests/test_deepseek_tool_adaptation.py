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

    # 6. terminal alias
    entry = registry._entries.get("terminal")
    assert entry is not None
    assert entry.alias_for == "run_command"
    args = {"command": "git status", "timeout": 30}
    err = _prepare_public_builtin_args(entry, args)
    assert err == "", f"Expected success but got {err}"
    assert args.get("cmd") == "git status"
    assert args.get("timeout_sec") == 30
    assert "command" not in args

    # 7. promote_chat_to_task & route_to_project
    entry = registry._entries.get("promote_chat_to_task")
    assert entry is not None
    args = {"objective": "build something", "parent_task_id": "task_123"}
    err = _prepare_public_builtin_args(entry, args)
    assert err == "", f"Expected success but got {err}"
    assert args.get("predecessor_task_id") == "task_123"

    entry = registry._entries.get("route_to_project")
    assert entry is not None
    args = {"message": "hello project", "task_id": "task_456"}
    err = _prepare_public_builtin_args(entry, args)
    assert err == "", f"Expected success but got {err}"
    assert args.get("predecessor_task_id") == "task_456"


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


def test_str_match_replace_multiline_generic_first_line():
    from ouroboros.tools.core import _str_match_replace

    text = """try:
    first_try()
except:
    pass

# ... many lines ...
try:
    distinctive_target_call(arg1, arg2)
except:
    pass
"""
    old_str = """try:
    distinctive_target_call(arg1, arg2_typo)
except:
    pass"""
    new_text, err = _str_match_replace(
        text, old_str, "replacement", "demo.py", "STR_REPLACE_ERROR"
    )
    assert new_text is None
    assert "⚠️ STR_REPLACE_ERROR: old_str not found in demo.py." in err
    assert "Nearest candidate match near line 7:" in err
    assert "distinctive_target_call" in err


def test_str_match_replace_crlf_normalization():
    from ouroboros.tools.core import _str_match_replace

    text = "line 1\r\nline 2 target\r\nline 3\r\n"
    new_text, err = _str_match_replace(
        text,
        "line 2 target typo\n",
        "replacement",
        "demo.py",
        "STR_REPLACE_ERROR"
    )
    assert new_text is None
    assert "Nearest candidate match near line 2:" in err
    assert "line 2 target" in err


def test_derive_refreshed_anchor_paraphrase():
    """ibl-05a306fdb5c9 (A5): auto-refresh anchor derives real byte-exact anchor from paraphrase."""
    from ouroboros.tools.core import _derive_refreshed_anchor

    text = """def promote_step():
    candidate = {"promote": true, "task_id": "abc"}
    return candidate
"""
    # Summary/scratchpad paraphrase corrupted boolean literal
    paraphrased = 'candidate = {"promote": bool, "task_id": "abc"}'
    refreshed = _derive_refreshed_anchor(text, paraphrased)
    assert refreshed is not None
    assert refreshed == '    candidate = {"promote": true, "task_id": "abc"}'


def test_derive_refreshed_anchor_returns_none_when_ambiguous():
    """ibl-05a306fdb5c9 (A5): ambiguous or multi-occurrence candidate does not auto-refresh."""
    from ouroboros.tools.core import _derive_refreshed_anchor

    text = "duplicate line\nduplicate line\n"
    refreshed = _derive_refreshed_anchor(text, "duplicate line typo")
    assert refreshed is None


def test_derive_refreshed_anchor_multiline_with_blank_lines():
    """ibl-05a306fdb5c9 (A5): multiline block with blank lines does not truncate trailing lines."""
    from ouroboros.tools.core import _derive_refreshed_anchor, _str_match_replace

    text = """def calculate(a, b):

    result = a + b

    return result
"""
    paraphrased = """def calculate(a, b):

    result = a + b_typo

    return result"""

    refreshed = _derive_refreshed_anchor(text, paraphrased)
    assert refreshed is not None
    # Must cover full 5-line block, not just first 3 lines
    assert "return result" in refreshed
    assert refreshed.startswith("def calculate(a, b):")

    new_text, err = _str_match_replace(
        text,
        refreshed,
        """def calculate(a, b):

    result = a + b_fixed

    return result""",
        "demo.py",
        "EDIT_TEXT_ERROR",
    )
    assert err is None
    assert new_text.count("return result") == 1


def test_derive_refreshed_anchor_subline_expression_preserves_indentation():
    """ibl-05a306fdb5c9 (A5): unindented expression anchor preserves line indentation."""
    from ouroboros.tools.core import _derive_refreshed_anchor, _str_match_replace

    text = """def sample():
    task = {
        "promote": True,
        "task_id": "123",
    }
"""
    # Paraphrased unindented anchor
    paraphrased = '"promote": bool,'
    refreshed = _derive_refreshed_anchor(text, paraphrased)
    assert refreshed is not None
    assert refreshed == '        "promote": True,'

    new_text, err = _str_match_replace(
        text, refreshed, '        "promote": False,', "demo.py", "EDIT_TEXT_ERROR"
    )
    assert err is None
    assert '        "promote": False,\n' in new_text


def test_derive_refreshed_anchor_ambiguous_functions_returns_none():
    """ibl-05a306fdb5c9 (A5): two distinct functions matching equally close return None."""
    from ouroboros.tools.core import _derive_refreshed_anchor

    text = """def func_one():
    return 1

def func_two():
    return 1
"""
    # Equally similar to func_one and func_two
    paraphrased = """def func_typo():
    return 1"""

    refreshed = _derive_refreshed_anchor(text, paraphrased)
    assert refreshed is None


def test_dsml_marker_sanitization_in_tool_args(tmp_path):
    """ibl-1a54916dc5fe / ibl-f208daef458a: sanitize stray DSML tokens from tool args."""
    registry = ToolRegistry(repo_dir=tmp_path, drive_root=tmp_path)
    entry = registry._entries.get("read_file")
    assert entry is not None

    args = {
        "path": "runtime_data:memory/knowledge/improvement-backlog.md｜DSML｜parameter>",
        "root": "runtime_data｜DSML｜",
    }
    err = _prepare_public_builtin_args(entry, args)
    assert err == "", f"Expected success but got: {err}"
    assert args["root"] == "runtime_data"
    assert args["path"] == "memory/knowledge/improvement-backlog.md"


def test_root_path_colon_separation_and_prefix_check(tmp_path):
    """ibl-1a54916dc5fe: separate root:path prefix and detect literal root prefixes."""
    registry = ToolRegistry(repo_dir=tmp_path, drive_root=tmp_path)
    entry = registry._entries.get("search_code")
    assert entry is not None

    args = {
        "query": "some_func",
        "path": "active_workspace:src/main.py",
    }
    err = _prepare_public_builtin_args(entry, args)
    assert err == "", f"Expected success but got: {err}"
    assert args["root"] == "active_workspace"
    assert args["path"] == "src/main.py"


def test_additional_tool_arg_aliases(tmp_path):
    """ibl-2556760eae99: aliases for list_files, search_code, plan_task."""
    registry = ToolRegistry(repo_dir=tmp_path, drive_root=tmp_path)

    # list_files with name or dir
    entry = registry._entries.get("list_files")
    assert entry is not None
    args1 = {"name": "subfolder"}
    err1 = _prepare_public_builtin_args(entry, args1)
    assert err1 == ""
    assert args1.get("path") == "subfolder"
    assert "name" not in args1

    args2 = {"dir": "subfolder2"}
    err2 = _prepare_public_builtin_args(entry, args2)
    assert err2 == ""
    assert args2.get("path") == "subfolder2"
    assert "dir" not in args2

    # search_code with dir
    entry_search = registry._entries.get("search_code")
    assert entry_search is not None
    args_search = {"query": "test", "dir": "pkg"}
    err_search = _prepare_public_builtin_args(entry_search, args_search)
    assert err_search == ""
    assert args_search.get("path") == "pkg"
    assert "dir" not in args_search

    # plan_task with task / description
    entry_plan = registry._entries.get("plan_task")
    assert entry_plan is not None
    args_plan = {"goal": "achieve X", "task": "step 1 then step 2"}
    err_plan = _prepare_public_builtin_args(entry_plan, args_plan)
    assert err_plan == ""
    assert args_plan.get("plan") == "step 1 then step 2"
    assert "task" not in args_plan
    assert "spec" in args_plan
    assert args_plan["spec"]["affected_paths"] == []


def test_verify_and_record_dict_wrapped_check(tmp_path):
    """ibl-d5d2291e525f: dict-wrapped check in verify_and_record is normalized."""
    registry = ToolRegistry(repo_dir=tmp_path, drive_root=tmp_path)
    entry = registry._entries.get("verify_and_record")
    assert entry is not None

    args = {
        "contract_kind": "explicit_command",
        "check": {"cmd": "pytest -q tests/test_foo.py"},
    }
    err = _prepare_public_builtin_args(entry, args)
    assert err == "", f"Expected success but got: {err}"
    assert args["check"] == "pytest -q tests/test_foo.py"


def test_repeated_argument_error_detection(tmp_path):
    """ibl-1be732176468: detect byte-identical tool-arg error repetition."""
    registry = ToolRegistry(repo_dir=tmp_path, drive_root=tmp_path)
    entry = registry._entries.get("read_file")
    assert entry is not None

    # Missing required argument 'path'
    args1 = {"nonexistent_arg": "foo"}
    err1 = _prepare_public_builtin_args(entry, args1, ctx=registry._ctx)
    assert "TOOL_ARG_ERROR" in err1
    assert "unsupported argument(s): nonexistent_arg" in err1

    # Call again with identical invalid args
    args2 = {"nonexistent_arg": "foo"}
    err2 = _prepare_public_builtin_args(entry, args2, ctx=registry._ctx)
    assert "REPEATED_ARGUMENT_ERROR" in err2
    assert "identical malformed arguments were already rejected" in err2




