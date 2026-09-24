"""ANSI styling, colors, and terminal formatting utilities."""

from __future__ import annotations

import os
import re
import shutil
import sys
from typing import Optional

_ANSI_ESCAPE_RE = re.compile(
    r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])"  # Standard ANSI escapes
    r"|\?\[[0-9;]*[a-zA-Z]"                   # Malformed ?[1m, ?[93m, ?[0m from dumb terminal replacement
    r"|\^\[\[[0-9;]*[a-zA-Z]"                 # Caret notation ^[[1m
)


def is_color_enabled() -> bool:
    """Check if color output is supported and not disabled by environment."""
    if os.environ.get("NO_COLOR", "").strip():
        return False
    if os.environ.get("OUROBOROS_NO_COLOR", "").strip() in ("1", "true", "yes"):
        return False
    if os.environ.get("FORCE_COLOR") or os.environ.get("CLICOLOR_FORCE"):
        return True
    term = str(os.environ.get("TERM", "")).strip().lower()
    if term in ("dumb", "", "unknown"):
        return False
    if not (hasattr(sys.stdout, "isatty") and sys.stdout.isatty()):
        return False
    try:
        from prompt_toolkit.output import create_output
        from prompt_toolkit.output.color_depth import ColorDepth
        out = create_output()
        if out.get_default_color_depth() == ColorDepth.DEPTH_1_BIT:
            return False
    except Exception:
        pass
    return True


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
    force: Optional[bool] = None,
) -> str:
    """Wrap text in ANSI formatting with automatic reset, or return plain text if unsupported."""
    if force is False or (force is None and not is_color_enabled()):
        return text
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


def clean_broken_escapes(text: str) -> str:
    """Sanitize any raw control escapes or ?[1m sequences, returning clean readable text."""
    if not text:
        return ""
    return _ANSI_ESCAPE_RE.sub("", text)


def cprint(text: str = "", end: str = "\n", file=None, flush: bool = False) -> None:
    """Hermes/Antigravity-parity formatted terminal print.

    Routes ANSI formatted strings through prompt_toolkit's output renderer or
    strips escapes if color is unsupported or disabled, preventing raw \\033
    escape sequences or ?[1m artifacts from corrupting output.
    """
    target_file = file or sys.stdout
    text_str = str(text)

    if target_file is not sys.stdout:
        out_text = strip_ansi(text_str) if not is_color_enabled() else text_str
        print(out_text, end=end, file=target_file, flush=flush)
        return

    if not is_color_enabled():
        print(strip_ansi(text_str), end=end, file=sys.stdout, flush=flush)
        return

    try:
        from prompt_toolkit import print_formatted_text as _pt_print
        from prompt_toolkit.formatted_text import ANSI as _PT_ANSI
        _pt_print(_PT_ANSI(text_str), end=end, flush=flush)
    except Exception:
        print(strip_ansi(text_str), end=end, file=sys.stdout, flush=flush)


def get_terminal_width(default: int = 80) -> int:
    """Return current terminal column width."""
    try:
        cols = shutil.get_terminal_size((default, 24)).columns
        return max(40, cols)
    except Exception:
        return default
