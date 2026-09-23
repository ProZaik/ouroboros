"""Implementations of Ouroboros CLI slash commands."""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, List, Optional

from ouroboros_cli.models.contracts import ChatMessage, DaemonState, TaskSummary
from ouroboros_cli.ui.ansi import Colors, Style, colorize
from ouroboros_cli.ui.widgets import (
    render_chat_message,
    render_decision_card,
    render_status_banner,
    render_task_table,
)

if TYPE_CHECKING:
    from ouroboros_cli.models.state import SessionState
    from ouroboros_cli.transport.client import OuroborosHTTPClient
    from ouroboros_cli.transport.websocket import OuroborosWSClient


def handle_help(args: List[str], state: SessionState, http_client: OuroborosHTTPClient, ws_client: Optional[OuroborosWSClient]) -> str:
    """Show help menu with available commands and hotkeys."""
    lines = [
        colorize("█▀ OUROBOROS INTERACTIVE CLI & REPL", Colors.BRIGHT_CYAN, bold=True),
        colorize("Type a message to chat directly with Ouroboros, or use slash commands:", Colors.WHITE),
        "",
        f"  {colorize('/status', Colors.BRIGHT_YELLOW, bold=True):<20} Inspect daemon health, mode, worker count, and budget",
        f"  {colorize('/tasks [all|run]', Colors.BRIGHT_YELLOW, bold=True):<20} List active tasks or filter (all/running/completed/failed)",
        f"  {colorize('/task <id>', Colors.BRIGHT_YELLOW, bold=True):<20} Show detailed information for a specific task",
        f"  {colorize('/projects', Colors.BRIGHT_YELLOW, bold=True):<20} List configured projects and their chat threads",
        f"  {colorize('/project <id>', Colors.BRIGHT_YELLOW, bold=True):<20} Switch current project context and chat thread",
        f"  {colorize('/cancel [id]', Colors.BRIGHT_YELLOW, bold=True):<20} Cancel a running task (defaults to current task)",
        f"  {colorize('/hurry [id]', Colors.BRIGHT_YELLOW, bold=True):<20} Accelerate execution of active task",
        f"  {colorize('/decision <opt>', Colors.BRIGHT_YELLOW, bold=True):<20} Answer pending quiz (number 1..N or text)",
        f"  {colorize('/mode [name]', Colors.BRIGHT_YELLOW, bold=True):<20} View or set runtime mode (e.g. standard, cyber_pro)",
        f"  {colorize('/model [name]', Colors.BRIGHT_YELLOW, bold=True):<20} View or switch active model from catalog",
        f"  {colorize('/history [n]', Colors.BRIGHT_YELLOW, bold=True):<20} View recent conversation history (default 10)",
        f"  {colorize('/logs [name]', Colors.BRIGHT_YELLOW, bold=True):<20} Tail runtime logs (progress, events, tools, supervisor)",
        f"  {colorize('/health', Colors.BRIGHT_YELLOW, bold=True):<20} Check health of Ouroboros API, host service & DeepSeek bridge",
        f"  {colorize('/session', Colors.BRIGHT_YELLOW, bold=True):<20} Display active session details and chat thread state",
        f"  {colorize('/clear', Colors.BRIGHT_YELLOW, bold=True):<20} Clear terminal screen",
        f"  {colorize('/quit, /exit', Colors.BRIGHT_YELLOW, bold=True):<20} Exit the REPL",
        "",
        colorize("Hotkeys:", Colors.GRAY, bold=True),
        f"  {colorize('Ctrl+C', Colors.GRAY)}: Cancel current input or task",
        f"  {colorize('Ctrl+D', Colors.GRAY)}: Exit REPL",
        f"  {colorize('Tab', Colors.GRAY)}: Auto-complete slash commands",
        f"  {colorize('Up/Down', Colors.GRAY)}: Browse command history",
    ]
    return "\n".join(lines)


def handle_status(args: List[str], state: SessionState, http_client: OuroborosHTTPClient, ws_client: Optional[OuroborosWSClient]) -> str:
    """Fetch and display daemon status."""
    try:
        daemon_state = http_client.state()
        state.daemon_state = daemon_state
        import urllib.parse
        parsed = urllib.parse.urlparse(http_client.base_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 8765
        return render_status_banner(daemon_state, host, port)
    except Exception as exc:
        return colorize(f"Error fetching daemon status: {exc}", Colors.BRIGHT_RED)


def handle_tasks(args: List[str], state: SessionState, http_client: OuroborosHTTPClient, ws_client: Optional[OuroborosWSClient]) -> str:
    """List running and pending tasks, or all tasks with filter."""
    try:
        data = http_client.tasks_list()
        filter_mode = args[0].strip().lower() if args else ""

        if filter_mode in ("all", "--all", "-a"):
            tasks = data.get("all", [])
            header = "All Tasks"
        elif filter_mode in ("running", "run"):
            tasks = data.get("running", [])
            header = "Running Tasks"
        elif filter_mode in ("completed", "done"):
            tasks = data.get("completed", [])
            header = "Completed Tasks"
        elif filter_mode in ("failed", "fail"):
            tasks = data.get("failed", [])
            header = "Failed Tasks"
        else:
            active = data.get("running", []) + data.get("pending", [])
            if active:
                return render_task_table(active)
            recent = data.get("all", [])[:10]
            if not recent:
                return colorize("No active tasks running or pending.", Colors.GRAY)
            note = colorize("No active running tasks. Showing recent tasks (use /tasks all for full list):", Colors.GRAY)
            return f"{note}\n{render_task_table(recent)}"

        if not tasks:
            return colorize(f"No {header.lower()} found.", Colors.GRAY)
        return render_task_table(tasks)
    except Exception as exc:
        return colorize(f"Error listing tasks: {exc}", Colors.BRIGHT_RED)


def handle_task(args: List[str], state: SessionState, http_client: OuroborosHTTPClient, ws_client: Optional[OuroborosWSClient]) -> str:
    """Inspect specific task details."""
    task_id = args[0].strip() if args else (state.active_task_id or "")
    if not task_id:
        return colorize("Usage: /task <task_id>", Colors.BRIGHT_YELLOW)

    try:
        data = http_client.task_get(task_id)
        task_data = data.get("task", data) if isinstance(data.get("task"), dict) else data
        summary = TaskSummary.from_dict(data)

        status_l = summary.status.lower()
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

        model_exec = task_data.get("model_execution") if isinstance(task_data.get("model_execution"), dict) else {}
        model_name = model_exec.get("reported_model") or model_exec.get("used_model") or task_data.get("model") or "-"
        result_text = str(task_data.get("result") or "").strip()

        lines = [
            colorize(f"Task Details: {task_id}", Colors.BRIGHT_CYAN, bold=True),
            f"  Status:       {colorize(summary.status, status_color, bold=True)}",
            f"  Runtime:      {summary.runtime_sec:.1f}s",
            f"  Objective:    {summary.objective or '-'}",
            f"  Root Task:    {task_data.get('root_task_id') or summary.id}",
            f"  Parent Task:  {task_data.get('parent_task_id') or '-'}",
            f"  Project ID:   {task_data.get('project_id') or '-'}",
            f"  Chat Thread:  {task_data.get('chat_id') or 1}",
            f"  Model:        {model_name}",
            f"  Created At:   {summary.created_at or '-'}",
        ]
        if result_text:
            lines.append(f"  Result:       {colorize(result_text[:200], Colors.WHITE)}")
        return "\n".join(lines)
    except Exception as exc:
        return colorize(f"Error fetching task {task_id}: {exc}", Colors.BRIGHT_RED)


def handle_cancel(args: List[str], state: SessionState, http_client: OuroborosHTTPClient, ws_client: Optional[OuroborosWSClient]) -> str:
    """Cancel a running task."""
    task_id = args[0].strip() if args else (state.active_task_id or "")
    if not task_id:
        return colorize("No active task to cancel. Specify: /cancel <task_id>", Colors.BRIGHT_YELLOW)

    try:
        res = http_client.task_cancel(task_id)
        return colorize(f"✓ Task {task_id} cancellation requested: {res}", Colors.BRIGHT_GREEN)
    except Exception as exc:
        return colorize(f"Error cancelling task {task_id}: {exc}", Colors.BRIGHT_RED)


def handle_hurry(args: List[str], state: SessionState, http_client: OuroborosHTTPClient, ws_client: Optional[OuroborosWSClient]) -> str:
    """Hurry execution of active task."""
    task_id = args[0].strip() if args else (state.active_task_id or "")
    if not task_id:
        return colorize("No active task to hurry. Specify: /hurry <task_id>", Colors.BRIGHT_YELLOW)

    try:
        res = http_client.task_hurry(task_id)
        return colorize(f"✓ Task {task_id} hurry signal sent: {res}", Colors.BRIGHT_GREEN)
    except Exception as exc:
        return colorize(f"Error hurrying task {task_id}: {exc}", Colors.BRIGHT_RED)


def handle_decision(args: List[str], state: SessionState, http_client: OuroborosHTTPClient, ws_client: Optional[OuroborosWSClient]) -> str:
    """Answer pending decision/quiz."""
    quiz = state.get_latest_open_quiz()
    if not quiz:
        return colorize("No open decision currently waiting for an answer.", Colors.GRAY)

    if not args:
        return render_decision_card(quiz)

    choice_str = " ".join(args).strip()
    # Check if choice is an integer 1..N
    option_idx: Optional[int] = None
    comment: Optional[str] = None

    if choice_str.isdigit():
        val = int(choice_str)
        if 1 <= val <= len(quiz.options):
            option_idx = val - 1
        elif val == 0:
            return colorize("Option 0 selected: Please provide comment text: /decision <your answer text>", Colors.BRIGHT_YELLOW)
        else:
            return colorize(f"Invalid option {val}. Choose 1..{len(quiz.options)} or write custom text.", Colors.BRIGHT_RED)
    else:
        # Verbatim comment
        comment = choice_str

    try:
        res = http_client.decision_answer(
            decision_id=quiz.decision_id,
            option_index=option_idx,
            comment=comment,
        )
        state.resolve_quiz(quiz.quiz_id, answered_index=option_idx, comment=comment)
        ans_repr = f"Option {option_idx + 1}" if option_idx is not None else f"Verbatim: {comment}"
        return colorize(f"✓ Decision answered ({ans_repr}): {res.get('status', 'ok')}", Colors.BRIGHT_GREEN, bold=True)
    except Exception as exc:
        return colorize(f"Error submitting decision: {exc}", Colors.BRIGHT_RED)


def handle_mode(args: List[str], state: SessionState, http_client: OuroborosHTTPClient, ws_client: Optional[OuroborosWSClient]) -> str:
    """View or change runtime mode."""
    if not args:
        try:
            cur_state = http_client.state()
            return f"Current runtime mode: {colorize(cur_state.runtime_mode or 'default', Colors.BRIGHT_CYAN, bold=True)}"
        except Exception as exc:
            return colorize(f"Error reading mode: {exc}", Colors.BRIGHT_RED)

    new_mode = args[0].strip().lower()
    try:
        res = http_client.owner_runtime_mode(new_mode)
        return colorize(f"✓ Runtime mode switched to '{new_mode}': {res}", Colors.BRIGHT_GREEN)
    except Exception as exc:
        return colorize(f"Error setting runtime mode: {exc}", Colors.BRIGHT_RED)


def handle_model(args: List[str], state: SessionState, http_client: OuroborosHTTPClient, ws_client: Optional[OuroborosWSClient]) -> str:
    """View or select model from catalog."""
    if not args:
        try:
            settings = http_client.settings_get()
            cur_model = settings.get("OUROBOROS_MODEL") or "default"
            catalog = http_client.model_catalog()
            items = catalog.get("items") or catalog.get("models") or []
            lines = [
                f"Active model: {colorize(str(cur_model), Colors.BRIGHT_CYAN, bold=True)}",
                colorize("Available models in catalog:", Colors.WHITE),
            ]
            for item in items[:15]:
                name = item.get("name") or item.get("id") or str(item)
                lines.append(f"  • {name}")
            if len(items) > 15:
                lines.append(f"  ... and {len(items) - 15} more. Use /model <name> to set.")
            return "\n".join(lines)
        except Exception as exc:
            return colorize(f"Error querying model catalog: {exc}", Colors.BRIGHT_RED)

    new_model = " ".join(args).strip()
    try:
        res = http_client.settings_post({"OUROBOROS_MODEL": new_model})
        return colorize(f"✓ Model set to '{new_model}': {res}", Colors.BRIGHT_GREEN)
    except Exception as exc:
        return colorize(f"Error updating model: {exc}", Colors.BRIGHT_RED)


def handle_history(args: List[str], state: SessionState, http_client: OuroborosHTTPClient, ws_client: Optional[OuroborosWSClient]) -> str:
    """View recent chat history."""
    limit = 10
    if args and args[0].isdigit():
        limit = int(args[0])

    try:
        messages = http_client.chat_history(limit=limit, chat_id=state.chat_id)
        valid_msgs = []
        for m in messages:
            msg_obj = ChatMessage.from_dict(m)
            if msg_obj.content.strip():
                valid_msgs.append(msg_obj)

        if not valid_msgs:
            return colorize("No chat history available.", Colors.GRAY)

        out_lines: List[str] = [colorize(f"--- Chat History (Last {len(valid_msgs)}) ---", Colors.GRAY)]
        for msg_obj in valid_msgs:
            out_lines.append(render_chat_message(msg_obj, render_md=True))
        return "\n".join(out_lines)
    except Exception as exc:
        return colorize(f"Error fetching history: {exc}", Colors.BRIGHT_RED)


def handle_projects(args: List[str], state: SessionState, http_client: OuroborosHTTPClient, ws_client: Optional[OuroborosWSClient]) -> str:
    """List projects or switch project scope (/project <id|name>)."""
    try:
        projects = http_client.projects_list()
        if not args:
            if not projects:
                return colorize("No projects configured.", Colors.GRAY)
            lines = [colorize("Available Projects:", Colors.BRIGHT_CYAN, bold=True)]
            for p in projects:
                pid = p.get("id", "")
                name = p.get("name", pid)
                chat_id = p.get("chat_id", 1)
                is_active = (state.project_id == pid)
                marker = colorize("▶ ", Colors.BRIGHT_GREEN) if is_active else "  "
                lines.append(f"{marker}{colorize(name, Colors.BRIGHT_WHITE, bold=is_active)} ({colorize(pid, Colors.GRAY)}, chat_id={chat_id})")
            lines.append(colorize("\nUse /project <id|name> to switch project, or /project main for default.", Colors.GRAY))
            return "\n".join(lines)

        target = " ".join(args).strip()
        if target.lower() in ("main", "root", "default", "none"):
            state.set_project("", chat_id=1)
            return colorize("✓ Switched to main project chat thread (chat_id=1).", Colors.BRIGHT_GREEN, bold=True)

        matched = None
        for p in projects:
            if p.get("id") == target or p.get("name", "").lower() == target.lower():
                matched = p
                break

        if matched:
            pid = matched.get("id", "")
            cid = int(matched.get("chat_id") or 1)
            state.set_project(pid, chat_id=cid)
            return colorize(f"✓ Switched to project '{matched.get('name', pid)}' (id={pid}, chat_id={cid}).", Colors.BRIGHT_GREEN, bold=True)
        else:
            return colorize(f"Project '{target}' not found. Use /projects to list available projects.", Colors.BRIGHT_RED)
    except Exception as exc:
        return colorize(f"Error managing projects: {exc}", Colors.BRIGHT_RED)


def handle_logs(args: List[str], state: SessionState, http_client: OuroborosHTTPClient, ws_client: Optional[OuroborosWSClient]) -> str:
    """Tail runtime logs."""
    name = args[0].strip() if args else "progress"
    limit = int(args[1]) if len(args) > 1 and args[1].isdigit() else 20

    try:
        data = http_client.logs_tail(name=name, limit=limit)
        entries = data.get("entries") or []
        if not entries:
            return colorize(f"No log entries found for '{name}'.", Colors.GRAY)

        lines = [colorize(f"--- Log Tail: {name} ({len(entries)} entries) ---", Colors.GRAY)]
        for entry in entries:
            msg = entry.get("message") or entry.get("content") or str(entry)
            ts = entry.get("ts") or ""
            ts_str = f"[{ts[:19]}] " if ts else ""
            lines.append(f"{colorize(ts_str, Colors.GRAY)}{msg}")
        return "\n".join(lines)
    except Exception as exc:
        return colorize(f"Error tailing logs for {name}: {exc}", Colors.BRIGHT_RED)


def handle_clear(args: List[str], state: SessionState, http_client: OuroborosHTTPClient, ws_client: Optional[OuroborosWSClient]) -> str:
    """Clear terminal screen."""
    os.system("clear" if os.name == "posix" else "cls")
    return ""


def handle_health(args: List[str], state: SessionState, http_client: OuroborosHTTPClient, ws_client: Optional[OuroborosWSClient]) -> str:
    """Check health of Ouroboros API, host service, DeepSeek bridge, and system environment."""
    import socket
    lines = [
        colorize("█▀ OUROBOROS SYSTEM HEALTH & SERVICE AUDIT", Colors.BRIGHT_CYAN, bold=True),
        "",
    ]

    def check_port(host: str, port: int, name: str) -> str:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.5)
        try:
            res = s.connect_ex((host, port))
            s.close()
            if res == 0:
                return f"  {colorize('● ONLINE', Colors.BRIGHT_GREEN, bold=True):<18} {colorize(name, Colors.BRIGHT_WHITE)} ({host}:{port})"
            return f"  {colorize('○ OFFLINE', Colors.BRIGHT_RED, bold=True):<18} {colorize(name, Colors.BRIGHT_WHITE)} ({host}:{port})"
        except Exception as exc:
            return f"  {colorize('✗ ERROR', Colors.BRIGHT_RED, bold=True):<18} {colorize(name, Colors.BRIGHT_WHITE)}: {exc}"

    lines.append(check_port("127.0.0.1", 8765, "Ouroboros Core API Gateway"))
    lines.append(check_port("127.0.0.1", 8767, "Ouroboros Host Service"))
    lines.append(check_port("127.0.0.1", 8318, "DeepSeek Bridge (Port 8318)"))
    lines.append(check_port("127.0.0.1", 8317, "Antigravity Bridge (Port 8317)"))

    try:
        health = http_client.health()
        lines.append("")
        lines.append(f"  Daemon Version:    {colorize(str(health.get('version', '?')), Colors.BRIGHT_YELLOW)}")
        lines.append(f"  Daemon Status:     {colorize(str(health.get('status', 'ok')), Colors.BRIGHT_GREEN)}")
    except Exception:
        pass

    import platform
    lines.append("")
    lines.append(f"  Runtime Python:    {colorize(sys.version.split()[0], Colors.BRIGHT_CYAN)} ({platform.platform()})")
    lines.append(f"  Execution Mode:    {colorize('Native Termux' if 'com.termux' in sys.executable else 'PRoot / Host', Colors.BRIGHT_GREEN, bold=True)}")
    return "\n".join(lines)


def handle_session(args: List[str], state: SessionState, http_client: OuroborosHTTPClient, ws_client: Optional[OuroborosWSClient]) -> str:
    """Display active session details and chat thread state."""
    lines = [
        colorize("█▀ REPL SESSION STATE", Colors.BRIGHT_CYAN, bold=True),
        f"  Chat Thread ID:     {colorize(str(state.chat_id), Colors.BRIGHT_GREEN)}",
        f"  Project ID:         {colorize(str(state.project_id or '(global root)'), Colors.BRIGHT_YELLOW)}",
        f"  WebSocket Status:   {colorize('CONNECTED' if state.connected else 'DISCONNECTED', Colors.BRIGHT_GREEN if state.connected else Colors.BRIGHT_RED)}",
        f"  Messages in Memory: {colorize(str(len(state.history)), Colors.WHITE)}",
    ]
    if state.active_task_id:
        lines.append(f"  Active Task ID:     {colorize(state.active_task_id, Colors.BRIGHT_MAGENTA)}")
    return "\n".join(lines)

