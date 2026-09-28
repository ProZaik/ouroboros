"""Regression tests for skill_payload argument aliasing in tool_resolution (ibl-11f392dc31a9, ibl-be898650cb2b).

Asserts that when root='skill_payload', passing name='...' or skill='...' is
cleanly aliased to skill_name='...' rather than being stolen by path='...' or
rejected with 'root=skill_payload requires a non-empty skill_name'.
"""
from __future__ import annotations

import pytest

from ouroboros.tools.core import get_tools
from ouroboros.tools.tool_resolution import _normalize_tool_call_args


@pytest.fixture
def tools_map():
    return {t.name: t for t in get_tools()}


def test_list_files_skill_payload_name_aliased_to_skill_name(tools_map):
    entry = tools_map["list_files"]
    args = {"root": "skill_payload", "bucket": "external", "name": "drovosek"}
    _normalize_tool_call_args(entry, args)

    assert args.get("skill_name") == "drovosek"
    assert "name" not in args
    # path must not have been clobbered by name
    assert args.get("path") in (None, ".")


def test_list_files_skill_payload_skill_aliased_to_skill_name(tools_map):
    entry = tools_map["list_files"]
    args = {"root": "skill_payload", "bucket": "native", "skill": "stand-executor", "path": "scripts"}
    _normalize_tool_call_args(entry, args)

    assert args.get("skill_name") == "stand-executor"
    assert "skill" not in args
    assert args.get("path") == "scripts"


def test_read_file_skill_payload_name_aliased_to_skill_name(tools_map):
    entry = tools_map["read_file"]
    args = {"root": "skill_payload", "bucket": "external", "name": "drovosek", "path": "SKILL.md"}
    _normalize_tool_call_args(entry, args)

    assert args.get("skill_name") == "drovosek"
    assert args.get("path") == "SKILL.md"


def test_list_files_regular_root_name_still_maps_to_path(tools_map):
    """Pin non-vacuity / backward compatibility: for non-skill_payload roots, name='foo' still maps to path='foo'."""
    entry = tools_map["list_files"]
    args = {"root": "active_workspace", "name": "src/master"}
    _normalize_tool_call_args(entry, args)

    assert args.get("path") == "src/master"
    assert "skill_name" not in args
