"""ANSI styling, colors, and terminal formatting utilities."""

from __future__ import annotations

import os
import re
import shutil
from typing import Optional

_ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"

    # Standard colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Bright colors
    GRAY = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"

    # Backgrounds
    BG_DARK = "\033[48;5;236m"
    BG_BLUE = "\033[44m"
    BG_CYAN = "\033[46m"
    BG_YELLOW = "\033[43m"


class Style:
    # Semantic roles
    PRIMARY = Colors.BRIGHT_CYAN
    SECONDARY = Colors.BLUE
    SUCCESS = Colors.BRIGHT_GREEN
    WARNING = Colors.BRIGHT_YELLOW
    ERROR = Colors.BRIGHT_RED
    MUTED = Colors.GRAY
    HEADER = Colors.BRIGHT_WHITE + Colors.BOLD
    ACCENT = Colors.BRIGHT_MAGENTA


def colorize(
    text: str,
    color: str = "",
    bold: bool = False,
    dim: bool = False,
    italic: bool = False,
    underline: bool = False,
) -> str:
    """Wrap text in ANSI formatting with automatic reset."""
    prefix = ""
    if bold:
        prefix += Colors.BOLD
    if dim:
        prefix += Colors.DIM
    if italic:
        prefix += Colors.ITALIC
    if underline:
        prefix += Colors.UNDERLINE
    if color:
        prefix += color
    if not prefix:
        return text
    return f"{prefix}{text}{Colors.RESET}"


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text to compute true display length."""
    return _ANSI_ESCAPE_RE.sub("", text)


def get_terminal_width(default: int = 80) -> int:
    """Return current terminal column width."""
    try:
        cols = shutil.get_terminal_size((default, 24)).columns
        return max(40, cols)
    except Exception:
        return default
