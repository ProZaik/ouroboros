"""Terminal UI widgets: decision cards, tool activity badges, task tables, and chat messages."""

from __future__ import annotations

import datetime
from typing import Dict, List, Optional

from ouroboros_cli.models.contracts import ChatMessage, DaemonState, LogEvent, QuizItem, TaskSummary
from ouroboros_cli.ui.ansi import Colors, Style, clean_broken_escapes, colorize, get_terminal_width, is_color_enabled, strip_ansi
from ouroboros_cli.ui.markdown import render_markdown


def render_decision_card(quiz: QuizItem) -> str:
    """Render a highlighted decision/quiz card with selectable options."""
    width = min(get_terminal_width(), 80)
    lines: List[str] = []

    border_color = Colors.BRIGHT_YELLOW
    title = f" [DECISION REQUIRED: {quiz.quiz_id}] "
    top = "┌─" + colorize(title, Colors.BRIGHT_WHITE, bold=True) + "─" * max(0, width - len(title) - 4) + "┐"
    lines.append(colorize(top, border_color))

    # Question text
    lines.append(f"{colorize('│', border_color)} {colorize('Question:', Colors.BRIGHT_CYAN, bold=True)}")
    q_lines = quiz.question.strip().split("\n")
    for ql in q_lines:
        lines.append(f"{colorize('│', border_color)}   {ql}")

    # Stake or Assumption if present
    if quiz.stake:
        lines.append(f"{colorize('│', border_color)} {colorize('Stake:', Colors.BRIGHT_MAGENTA)} {quiz.stake}")
    if quiz.assumption:
        lines.append(f"{colorize('│', border_color)} {colorize('Default Assumption:', Colors.GRAY)} {quiz.assumption}")

    lines.append(f"{colorize('├', border_color)}" + colorize("─" * (width - 2), border_color) + f"{colorize('┤', border_color)}")
    lines.append(f"{colorize('│', border_color)} {colorize('Options (Type number to select or /decision <num|text>):', Colors.WHITE, bold=True)}")

    for opt in quiz.options:
        opt_num = f" [{opt.index + 1}] "
        num_str = colorize(opt_num, Colors.BRIGHT_GREEN, bold=True)
        lines.append(f"{colorize('│', border_color)}  {num_str} {opt.text}")

    # Free answer hint
    lines.append(f"{colorize('│', border_color)}  {colorize(' [0] ', Colors.GRAY)} (Write custom verbatim text answer)")

    # Bottom border
    bot = "└" + "─" * (width - 2) + "┘"
    lines.append(colorize(bot, border_color))

    return "\n".join(lines)


def render_tool_event(event: LogEvent) -> str:
    """Render tool execution activity line."""
    time_str = ""
    if event.ts:
        try:
            # Parse ISO timestamp
            ts_clean = event.ts.split(".")[0].replace("Z", "")
            time_str = ts_clean.split("T")[-1]
        except Exception:
            time_str = event.ts[:8]

    time_tag = colorize(f"[{time_str}] ", Colors.GRAY) if time_str else ""

    if event.tool:
        tool_badge = colorize(f"⚙ TOOL:{event.tool}", Colors.BRIGHT_MAGENTA, bold=True)
        action_text = colorize(event.message or event.event, Colors.BRIGHT_WHITE)
        return f"{time_tag}{tool_badge} {action_text}"

    # General log
    level = event.level.upper()
    lvl_color = Colors.BRIGHT_CYAN
    if level == "WARNING":
        lvl_color = Colors.BRIGHT_YELLOW
    elif level == "ERROR":
        lvl_color = Colors.BRIGHT_RED

    level_badge = colorize(f"[{level}]", lvl_color, bold=True)
    return f"{time_tag}{level_badge} {event.message}"


def render_task_table(tasks: List[TaskSummary]) -> str:
    """Render formatted table of tasks with precise visual column alignment."""
    if not tasks:
        return colorize("No active tasks found.", Colors.GRAY)

    width = get_terminal_width()
    lines: List[str] = []

    # Columns: ID, Status, Priority, Runtime, Objective
    headers = ["Task ID", "Status", "Sec", "Objective"]
    col_w = [18, 10, 6, max(20, width - 42)]

    top = "┌" + "┬".join("─" * (w + 2) for w in col_w) + "┐"
    lines.append(colorize(top, Colors.GRAY))

    # Header row
    hdr_cells = [f" {colorize(h, Colors.BRIGHT_WHITE, bold=True)}{' ' * (col_w[i] - len(h))} " for i, h in enumerate(headers)]
    lines.append(colorize("│", Colors.GRAY) + colorize("│", Colors.GRAY).join(hdr_cells) + colorize("│", Colors.GRAY))

    sep = "├" + "┼".join("─" * (w + 2) for w in col_w) + "┤"
    lines.append(colorize(sep, Colors.GRAY))

    for t in tasks:
        status_l = t.status.lower()
        if status_l == "running":
            status_color = Colors.BRIGHT_GREEN
        elif status_l == "completed":
            status_color = Colors.BRIGHT_CYAN
        elif status_l == "failed":
            status_color = Colors.BRIGHT_RED
        elif status_l in ("cancelled", "canceled"):
            status_color = Colors.GRAY
        else:
            status_color = Colors.BRIGHT_YELLOW

        disp_status = t.status[:col_w[1]]
        status_str = colorize(disp_status, status_color, bold=True)

        obj_clean = " ".join(t.objective.split())
        if len(obj_clean) > col_w[3]:
            obj_clean = obj_clean[: col_w[3] - 3] + "..."

        sec_str = f"{int(t.runtime_sec)}s"
        sec_pad = max(0, col_w[2] - len(sec_str))
        sec_cell = " " * sec_pad + colorize(sec_str, Colors.GRAY)

        id_disp = t.id[:col_w[0]]
        id_cell = colorize(id_disp, Colors.BRIGHT_CYAN) + " " * max(0, col_w[0] - len(id_disp))

        stat_cell = status_str + " " * max(0, col_w[1] - len(disp_status))

        obj_pad = max(0, col_w[3] - len(obj_clean))
        obj_cell = obj_clean + " " * obj_pad

        row_cells = [
            f" {id_cell} ",
            f" {stat_cell} ",
            f" {sec_cell} ",
            f" {obj_cell} ",
        ]
        lines.append(colorize("│", Colors.GRAY) + colorize("│", Colors.GRAY).join(row_cells) + colorize("│", Colors.GRAY))

    bot = "└" + "┴".join("─" * (w + 2) for w in col_w) + "┘"
    lines.append(colorize(bot, Colors.GRAY))

    return "\n".join(lines)


def render_status_banner(state: DaemonState, host: str, port: int) -> str:
    """Render daemon health and runtime status panel."""
    width = min(get_terminal_width(), 80)
    lines: List[str] = []

    border = Colors.CYAN
    title = f" [OUROBOROS DAEMON: {host}:{port}] "
    top = "┌─" + colorize(title, Colors.BRIGHT_WHITE, bold=True) + "─" * max(0, width - len(title) - 4) + "┐"
    lines.append(colorize(top, border))

    col1 = f"Runtime: {colorize(state.runtime_mode or 'default', Colors.BRIGHT_CYAN, bold=True)}"
    col2 = f"Workers: {colorize(f'{state.workers_alive}/{state.workers_total}', Colors.BRIGHT_GREEN)}"
    col3 = f"Tasks: {colorize(f'run={state.running_count}, pend={state.pending_count}', Colors.BRIGHT_YELLOW)}"
    lines.append(f"{colorize('│', border)}  {col1:<32} {col2:<20} {col3}")

    col4 = f"Branch: {colorize(state.branch or 'main', Colors.GRAY)}"
    col5 = f"SHA: {colorize(state.sha[:8] if state.sha else 'unknown', Colors.GRAY)}"
    col6 = f"Budget: {colorize(f'${state.spent_usd:.2f} / ${state.budget_limit:.2f}', Colors.BRIGHT_MAGENTA)}"
    lines.append(f"{colorize('│', border)}  {col4:<32} {col5:<20} {col6}")

    bot = "└" + "─" * (width - 2) + "┘"
    lines.append(colorize(bot, border))

    return "\n".join(lines)


import re

_SPECIAL_TOKEN_RE = re.compile(r"<[｜|][^｜|>]+[｜|]>")
_DSML_INVOKE_RE = re.compile(r"<[｜|]DSML[｜|]invoke\s+name=[\"']([^\"']+)[\"']>(.*?)</[｜|]DSML[｜|]invoke>", re.DOTALL)
_DSML_PARAM_RE = re.compile(r"<[｜|]DSML[｜|]parameter\s+name=[\"']([^\"']+)[\"'][^>]*>(.*?)</[｜|]DSML[｜|]parameter>", re.DOTALL)
_DSML_TAG_RE = re.compile(r"</?[｜|]DSML[｜|][^>]*>")
_TOOL_RESULT_RE = re.compile(r"<tool_result>(.*?)</tool_result>", re.DOTALL)


def clean_terminal_content(text: str) -> str:
    """Sanitize raw LLM stream text for human terminal display."""
    if not text:
        return ""

    def _fmt_invoke(m):
        tool = m.group(1)
        params = []
        for p in _DSML_PARAM_RE.finditer(m.group(2)):
            val = p.group(2).strip()
            if len(val) > 40:
                val = val[:37] + "..."
            params.append(f"{p.group(1)}={val}")
        p_str = f" ({', '.join(params)})" if params else ""
        return f"\n[⚙ {tool}{p_str}]\n"

    res = _DSML_INVOKE_RE.sub(_fmt_invoke, text)
    res = _DSML_TAG_RE.sub("", res)
    res = _SPECIAL_TOKEN_RE.sub("", res)
    res = _TOOL_RESULT_RE.sub(lambda m: f"[tool_result: {len(m.group(1))} chars]", res)
    res = clean_broken_escapes(res)
    return res.strip()


def render_chat_message(msg: ChatMessage, render_md: bool = True) -> str:
    """Render chat frame into styled terminal block."""
    role = msg.role.lower()
    raw_cleaned = clean_terminal_content(msg.content)

    if role == "user":
        prefix = colorize("❯ USER", Colors.BRIGHT_GREEN, bold=True)
        return f"\n{prefix}:\n{raw_cleaned}\n"

    elif role == "assistant":
        if msg.is_progress:
            prefix = colorize("💬 [progress]", Colors.CYAN)
            return f"{prefix} {raw_cleaned}"
        task_info = f" (task: {msg.task_id[:8]})" if msg.task_id else ""
        prefix = colorize(f"✦ OUROBOROS{task_info}", Colors.BRIGHT_CYAN, bold=True)
        content = render_markdown(raw_cleaned) if (render_md and msg.markdown) else raw_cleaned
        return f"\n{prefix}:\n{content}\n"

    else:  # system
        prefix = colorize("⚙ SYSTEM", Colors.BRIGHT_YELLOW, bold=True)
        content = render_markdown(raw_cleaned) if (render_md and msg.markdown and "\n" in raw_cleaned) else raw_cleaned
        return f"\n{prefix}: {content}\n"
