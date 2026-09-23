"""Interactive terminal prompt using prompt_toolkit."""

from __future__ import annotations

import os
import pathlib
from typing import List, Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style as PtStyle

SLASH_COMMANDS = [
    "/help",
    "/status",
    "/tasks",
    "/task",
    "/projects",
    "/project",
    "/cancel",
    "/hurry",
    "/decision",
    "/mode",
    "/model",
    "/history",
    "/logs",
    "/health",
    "/session",
    "/clear",
    "/quit",
    "/exit",
]


def create_prompt_session(history_file: Optional[str] = None) -> PromptSession:
    """Create a configured prompt_toolkit PromptSession with history and completions."""
    if history_file is None:
        cache_dir = pathlib.Path.home() / ".cache" / "ouroboros-cli"
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            history_file = str(cache_dir / "history.txt")
        except Exception:
            history_file = None

    history = FileHistory(history_file) if history_file else None
    completer = WordCompleter(SLASH_COMMANDS, sentence=True)

    pt_style = PtStyle.from_dict({
        "prompt": "ansicyan bold",
        "mode": "ansimagenta",
        "indicator": "ansigreen bold",
    })

    return PromptSession(
        history=history,
        completer=completer,
        auto_suggest=AutoSuggestFromHistory(),
        style=pt_style,
        enable_history_search=True,
    )
