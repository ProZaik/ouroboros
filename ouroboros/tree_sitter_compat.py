"""Compatibility layer for tree-sitter grammars (modular vs language pack)."""

from __future__ import annotations

import functools
import importlib
import sys
from typing import Any, Optional


def get_parser(grammar: str) -> Any:
    """Return a tree-sitter Parser for the requested grammar.

    Supports both monolithic tree_sitter_language_pack and modular
    tree_sitter_<grammar> packages (tree-sitter-python,
    tree-sitter-javascript, tree-sitter-json, tree-sitter-markdown).
    """
    # Allow tests to explicitly disable native parsers via sys.modules["tree_sitter_language_pack"] = None
    if sys.modules.get("tree_sitter_language_pack") is None and "tree_sitter_language_pack" in sys.modules:
        raise ImportError("tree_sitter_language_pack disabled via sys.modules")

    try:
        from tree_sitter_language_pack import get_parser as lp_get_parser
        return lp_get_parser(grammar)
    except (ImportError, ModuleNotFoundError):
        pass

    g = grammar.lower().replace("-", "_")
    if g == "js":
        g = "javascript"

    try:
        from tree_sitter import Language, Parser

        if g == "markdown":
            import tree_sitter_markdown as tsm
            return Parser(Language(tsm.language()))
        elif g == "markdown_inline":
            import tree_sitter_markdown as tsm
            return Parser(Language(tsm.inline_language()))
        elif g == "python":
            import tree_sitter_python as tspy
            return Parser(Language(tspy.language()))
        elif g in ("javascript", "js"):
            import tree_sitter_javascript as tsjs
            return Parser(Language(tsjs.language()))
        elif g == "json":
            import tree_sitter_json as tsjson
            return Parser(Language(tsjson.language()))
        else:
            mod_name = f"tree_sitter_{g}"
            mod = importlib.import_module(mod_name)
            lang_fn = getattr(mod, "language", None)
            if callable(lang_fn):
                return Parser(Language(lang_fn()))
    except Exception as exc:
        raise ImportError(f"No modular parser available for grammar '{grammar}': {exc}") from exc

    raise ImportError(f"No parser available for grammar '{grammar}'")
