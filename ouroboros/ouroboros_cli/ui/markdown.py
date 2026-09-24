"""Terminal Markdown renderer with Pygments syntax highlighting and unicode box styling."""

from __future__ import annotations

import re
from typing import List, Optional

from ouroboros_cli.ui.ansi import Colors, Style, colorize, get_terminal_width, is_color_enabled, strip_ansi

# Optional pygments integration
try:
    from pygments import highlight
    from pygments.lexers import get_lexer_by_name, guess_lexer
    from pygments.formatters import Terminal256Formatter
    _HAS_PYGMENTS = True
except ImportError:
    _HAS_PYGMENTS = False


def _highlight_code(code: str, language: str = "") -> str:
    """Highlight code block using Pygments or return formatted plain text."""
    if not is_color_enabled():
        return code
    if _HAS_PYGMENTS:
        try:
            if language:
                lexer = get_lexer_by_name(language, stripall=True)
            else:
                lexer = guess_lexer(code)
            formatter = Terminal256Formatter(style="monokai")
            highlighted = highlight(code, lexer, formatter).rstrip("\n")
            return highlighted
        except Exception:
            pass
    # Fallback syntax formatting
    return colorize(code, Colors.BRIGHT_WHITE)


def _render_table(table_lines: List[str]) -> str:
    """Render markdown table into clean unicode grid."""
    rows: List[List[str]] = []
    for line in table_lines:
        parts = [cell.strip() for cell in line.strip().strip("|").split("|")]
        # Skip separator rows like |---|---|
        if all(re.match(r"^:?-+:?$", cell) for cell in parts if cell):
            continue
        if any(parts):
            rows.append(parts)

    if not rows:
        return "\n".join(table_lines)

    col_count = max(len(row) for row in rows)
    # Normalize row lengths
    for row in rows:
        while len(row) < col_count:
            row.append("")

    # Determine column widths
    col_widths = [0] * col_count
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(strip_ansi(cell)))
    col_widths = [max(w, 3) for w in col_widths]

    out_lines: List[str] = []
    # Top border
    top = "┌" + "┬".join("─" * (w + 2) for w in col_widths) + "┐"
    out_lines.append(colorize(top, Colors.GRAY))

    for r_idx, row in enumerate(rows):
        cells_rendered = []
        for i, cell in enumerate(row):
            padding = col_widths[i] - len(strip_ansi(cell))
            if r_idx == 0:
                cell_text = colorize(cell, Colors.BRIGHT_WHITE, bold=True)
            else:
                cell_text = cell
            cells_rendered.append(f" {cell_text}{' ' * padding} ")
        line_str = colorize("│", Colors.GRAY) + colorize("│", Colors.GRAY).join(cells_rendered) + colorize("│", Colors.GRAY)
        out_lines.append(line_str)

        # Header separator
        if r_idx == 0:
            sep = "├" + "┼".join("─" * (w + 2) for w in col_widths) + "┤"
            out_lines.append(colorize(sep, Colors.GRAY))

    # Bottom border
    bot = "└" + "┴".join("─" * (w + 2) for w in col_widths) + "┘"
    out_lines.append(colorize(bot, Colors.GRAY))

    return "\n".join(out_lines)


def _render_inline(line: str) -> str:
    """Format inline markdown elements: bold, italic, inline code."""
    # Inline code `code`
    line = re.sub(
        r"`([^`]+)`",
        lambda m: colorize(f" {m.group(1)} ", Colors.BRIGHT_YELLOW, bold=False),
        line,
    )
    # Bold **text**
    line = re.sub(
        r"\*\*([^*]+)\*\*",
        lambda m: colorize(m.group(1), bold=True),
        line,
    )
    # Italic *text*
    line = re.sub(
        r"(?<!\*)\*([^*]+)\*(?!\*)",
        lambda m: colorize(m.group(1), italic=True),
        line,
    )
    # Links [title](url)
    line = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: f"{colorize(m.group(1), Colors.BRIGHT_BLUE, underline=True)} {colorize('(' + m.group(2) + ')', Colors.GRAY)}",
        line,
    )
    return line


def render_markdown(text: str) -> str:
    """Transform markdown text to formatted ANSI terminal output."""
    if not text:
        return ""

    lines = text.split("\n")
    output: List[str] = []
    width = get_terminal_width()

    in_code_block = False
    code_block_lang = ""
    code_block_lines: List[str] = []
    table_lines: List[str] = []

    for line in lines:
        stripped = line.strip()

        # Check for code block fence
        if stripped.startswith("```"):
            if in_code_block:
                # Close code block
                in_code_block = False
                code_content = "\n".join(code_block_lines)
                highlighted = _highlight_code(code_content, code_block_lang)
                # Box wrapper
                header_title = f" [{code_block_lang or 'code'}] "
                top_border = "┌──" + header_title + "─" * max(0, width - len(header_title) - 5) + "┐"
                output.append(colorize(top_border, Colors.GRAY))
                for c_line in highlighted.split("\n"):
                    output.append(f"{colorize('│', Colors.GRAY)} {c_line}")
                bot_border = "└" + "─" * (width - 2) + "┘"
                output.append(colorize(bot_border, Colors.GRAY))
                code_block_lines = []
                code_block_lang = ""
            else:
                # Open code block
                in_code_block = True
                code_block_lang = stripped[3:].strip().lower()
                code_block_lines = []
            continue

        if in_code_block:
            code_block_lines.append(line)
            continue

        # Check for table line
        if stripped.startswith("|") and stripped.endswith("|"):
            table_lines.append(stripped)
            continue
        elif table_lines:
            output.append(_render_table(table_lines))
            table_lines = []

        # Horizontal rule
        if re.match(r"^(\-{3,}|\*{3,}|_{3,})$", stripped):
            output.append(colorize("─" * min(width, 70), Colors.GRAY))
            continue

        # Headings
        if stripped.startswith("#"):
            match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
            if match:
                level = len(match.group(1))
                h_text = match.group(2)
                if level == 1:
                    output.append("")
                    output.append(colorize(f"=== {h_text.upper()} ===", Colors.BRIGHT_CYAN, bold=True))
                elif level == 2:
                    output.append("")
                    output.append(colorize(f"## {h_text}", Colors.BRIGHT_MAGENTA, bold=True))
                else:
                    output.append(colorize(f"{'#' * level} {h_text}", Colors.BRIGHT_YELLOW, bold=True))
                continue

        # Blockquote
        if stripped.startswith(">"):
            q_text = stripped[1:].strip()
            formatted_q = _render_inline(q_text)
            output.append(f"{colorize('│', Colors.BRIGHT_BLUE, bold=True)} {colorize(formatted_q, Colors.WHITE, italic=True)}")
            continue

        # Unordered list
        if re.match(r"^[-*+]\s+", stripped):
            item_text = re.sub(r"^[-*+]\s+", "", stripped)
            output.append(f"  {colorize('•', Colors.BRIGHT_CYAN)} {_render_inline(item_text)}")
            continue

        # Ordered list
        m_num = re.match(r"^(\d+)\.\s+(.*)$", stripped)
        if m_num:
            num = m_num.group(1)
            item_text = m_num.group(2)
            output.append(f"  {colorize(num + '.', Colors.BRIGHT_YELLOW)} {_render_inline(item_text)}")
            continue

        # Regular paragraph
        output.append(_render_inline(line))

    # Clean up trailing open structures
    if in_code_block and code_block_lines:
        code_content = "\n".join(code_block_lines)
        highlighted = _highlight_code(code_content, code_block_lang)
        for c_line in highlighted.split("\n"):
            output.append(f"{colorize('│', Colors.GRAY)} {c_line}")

    if table_lines:
        output.append(_render_table(table_lines))

    res = "\n".join(output)
    if not is_color_enabled():
        return strip_ansi(res)
    return res
