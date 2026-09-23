"""Command-line entrypoint for Ouroboros CLI and REPL."""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Optional, Sequence

from ouroboros_cli import __version__
from ouroboros_cli.config import CLIConfig
from ouroboros_cli.models.contracts import ChatMessage, LogEvent, QuizItem
from ouroboros_cli.models.state import SessionState
from ouroboros_cli.repl import OuroborosREPL
from ouroboros_cli.transport.client import OuroborosHTTPClient
from ouroboros_cli.transport.websocket import OuroborosWSClient
from ouroboros_cli.ui.ansi import Colors, Style, colorize
from ouroboros_cli.ui.widgets import (
    render_chat_message,
    render_decision_card,
    render_status_banner,
    render_task_table,
    render_tool_event,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ouroboros-cli",
        description="Interactive Streaming CLI and REPL for Ouroboros Autonomous Agent",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--host", default=None, help="Daemon server host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None, help="Daemon server port (default: 8765)")
    parser.add_argument("--chat-id", type=int, default=None, help="Chat thread ID (default: 1)")
    parser.add_argument("--project-id", default=None, help="Project scope ID")
    parser.add_argument("--no-markdown", action="store_true", help="Disable rich markdown formatting")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    subparsers = parser.add_subparsers(dest="subcommand")

    # repl (default)
    subparsers.add_parser("repl", help="Start interactive streaming REPL (default)")

    # status
    subparsers.add_parser("status", help="Show daemon runtime status and health")

    # tasks
    tasks_p = subparsers.add_parser("tasks", help="List running and pending tasks")
    tasks_p.add_argument("--all", "-a", action="store_true", help="List all tasks including completed and failed")
    tasks_p.add_argument("filter", nargs="?", default="", help="Filter: all, running, completed, failed")

    # task
    task_p = subparsers.add_parser("task", help="Show detailed information for a specific task")
    task_p.add_argument("task_id", help="Task ID to inspect")

    # projects
    subparsers.add_parser("projects", help="List configured projects and their chat threads")

    # chat
    chat_p = subparsers.add_parser("chat", help="Send a message and stream assistant response")
    chat_p.add_argument("message", nargs="+", help="Message text to send")

    # run
    run_p = subparsers.add_parser("run", help="Run a managed task and stream results")
    run_p.add_argument("prompt", nargs="+", help="Task description / prompt")
    run_p.add_argument("--workspace", default="", help="Workspace root directory")

    # cancel
    cancel_p = subparsers.add_parser("cancel", help="Cancel a running task")
    cancel_p.add_argument("task_id", help="Task ID to cancel")

    # hurry
    hurry_p = subparsers.add_parser("hurry", help="Hurry active task execution")
    hurry_p.add_argument("task_id", help="Task ID to hurry")

    # decide
    decide_p = subparsers.add_parser("decide", help="Submit answer to an owner decision")
    decide_p.add_argument("decision_id", help="Decision ID (e.g. quiz:task_id:quiz_id)")
    decide_p.add_argument("option", help="Option number (1..N) or verbatim text")

    return parser


async def _run_stream_chat(config: CLIConfig, message_text: str) -> int:
    """Send message via WebSocket, stream response until completion, then exit."""
    ws = OuroborosWSClient(url=config.ws_url)
    done_event = asyncio.Event()

    def on_chat(data):
        msg = ChatMessage.from_dict(data)
        if msg.role == "assistant":
            if msg.is_progress:
                if msg.content.strip():
                    print(render_chat_message(msg, render_md=config.render_markdown))
            else:
                if msg.content.strip():
                    rendered = render_chat_message(msg, render_md=config.render_markdown)
                    print(rendered)
                done_event.set()
        elif msg.role == "system" and msg.content.strip():
            print(render_chat_message(msg, render_md=config.render_markdown))

    def on_log(data):
        event = LogEvent.from_dict(data)
        if event.tool or event.level in ("warning", "error"):
            print(render_tool_event(event))

    def on_quiz(data):
        quiz = QuizItem.from_dict(data)
        print("\n" + render_decision_card(quiz) + "\n")

    ws.on("chat", on_chat)
    ws.on("log", on_log)
    ws.on("quiz", on_quiz)

    await ws.start()
    # Wait for connection
    for _ in range(50):
        if ws.is_connected:
            break
        await asyncio.sleep(0.1)

    if not ws.is_connected:
        print(colorize(f"Error: Could not connect to daemon at {config.ws_url}", Colors.BRIGHT_RED))
        await ws.stop()
        return 1

    print(colorize(f"❯ Sending: {message_text}", Colors.BRIGHT_GREEN))
    await ws.send_chat(message_text, chat_id=config.chat_id, project_id=config.project_id)

    try:
        # Wait for assistant response with a reasonable timeout
        await asyncio.wait_for(done_event.wait(), timeout=120.0)
    except asyncio.TimeoutError:
        print(colorize("Stream timed out after 120 seconds.", Colors.BRIGHT_YELLOW))
    finally:
        await ws.stop()

    return 0


async def _watch_task(config: CLIConfig, client: OuroborosHTTPClient, task_id: str) -> int:
    """Stream events for an active task via WebSocket and monitor completion."""
    ws = OuroborosWSClient(url=config.ws_url)
    done_event = asyncio.Event()

    def on_chat(data):
        msg = ChatMessage.from_dict(data)
        if msg.task_id and msg.task_id != task_id:
            return
        if msg.role == "assistant":
            if msg.is_progress:
                if msg.content.strip():
                    print(render_chat_message(msg, render_md=config.render_markdown))
            else:
                if msg.content.strip():
                    print(render_chat_message(msg, render_md=config.render_markdown))
                done_event.set()
        elif msg.role == "system" and msg.content.strip():
            print(render_chat_message(msg, render_md=config.render_markdown))

    def on_log(data):
        event = LogEvent.from_dict(data)
        if event.task_id and event.task_id != task_id:
            return
        if event.tool or event.level in ("warning", "error"):
            print(render_tool_event(event))

    def on_quiz(data):
        quiz = QuizItem.from_dict(data)
        if quiz.task_id == task_id:
            print("\n" + render_decision_card(quiz) + "\n")

    ws.on("chat", on_chat)
    ws.on("log", on_log)
    ws.on("quiz", on_quiz)

    await ws.start()

    terminal_status = "running"
    for _ in range(120):
        if done_event.is_set():
            break
        try:
            task_info = await asyncio.to_thread(client.task_get, task_id)
            status = str(task_info.get("status") or "").lower()
            if status in ("completed", "failed", "cancelled", "canceled"):
                terminal_status = status
                break
        except Exception:
            pass
        await asyncio.sleep(1.5)

    await ws.stop()

    status_color = Colors.BRIGHT_GREEN if terminal_status == "completed" else Colors.BRIGHT_RED
    print(colorize(f"\nTask {task_id} settled with status: {terminal_status}", status_color, bold=True))
    return 0 if terminal_status in ("completed", "running") else 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Main CLI entrypoint."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    config = CLIConfig.from_env(
        host=args.host,
        port=args.port,
        chat_id=args.chat_id,
        project_id=args.project_id,
    )
    if args.no_markdown:
        config.render_markdown = False
    if args.debug:
        config.debug = True

    client = OuroborosHTTPClient(base_url=config.http_base_url, timeout=config.timeout)

    # Subcommand dispatch
    sub = args.subcommand or "repl"

    if sub == "status":
        try:
            d_state = client.state()
            print(render_status_banner(d_state, config.host, config.port))
            return 0
        except Exception as exc:
            print(colorize(f"Error checking status: {exc}", Colors.BRIGHT_RED), file=sys.stderr)
            return 1

    elif sub == "tasks":
        try:
            tasks_data = client.tasks_list()
            filter_mode = getattr(args, "filter", "") or ("all" if getattr(args, "all", False) else "")
            if filter_mode:
                if filter_mode in ("all", "-a", "--all"):
                    tasks = tasks_data.get("all", [])
                else:
                    tasks = tasks_data.get(filter_mode.lower(), [])
                print(render_task_table(tasks))
            else:
                active = tasks_data.get("running", []) + tasks_data.get("pending", [])
                if active:
                    print(render_task_table(active))
                else:
                    recent = tasks_data.get("all", [])[:10]
                    if not recent:
                        print(colorize("No tasks found.", Colors.GRAY))
                    else:
                        print(colorize("No active running tasks. Showing recent tasks (use --all for full list):", Colors.GRAY))
                        print(render_task_table(recent))
            return 0
        except Exception as exc:
            print(colorize(f"Error listing tasks: {exc}", Colors.BRIGHT_RED), file=sys.stderr)
            return 1

    elif sub == "task":
        try:
            from ouroboros_cli.commands.handlers import handle_task
            state = SessionState(chat_id=config.chat_id, project_id=config.project_id)
            print(handle_task([args.task_id], state, client, None))
            return 0
        except Exception as exc:
            print(colorize(f"Error inspecting task: {exc}", Colors.BRIGHT_RED), file=sys.stderr)
            return 1

    elif sub == "projects":
        try:
            from ouroboros_cli.commands.handlers import handle_projects
            state = SessionState(chat_id=config.chat_id, project_id=config.project_id)
            print(handle_projects([], state, client, None))
            return 0
        except Exception as exc:
            print(colorize(f"Error listing projects: {exc}", Colors.BRIGHT_RED), file=sys.stderr)
            return 1

    elif sub == "cancel":
        try:
            res = client.task_cancel(args.task_id)
            print(colorize(f"✓ Task {args.task_id} cancellation requested: {res}", Colors.BRIGHT_GREEN))
            return 0
        except Exception as exc:
            print(colorize(f"Error cancelling task: {exc}", Colors.BRIGHT_RED), file=sys.stderr)
            return 1

    elif sub == "hurry":
        try:
            res = client.task_hurry(args.task_id)
            print(colorize(f"✓ Task {args.task_id} hurry signal sent: {res}", Colors.BRIGHT_GREEN))
            return 0
        except Exception as exc:
            print(colorize(f"Error hurrying task: {exc}", Colors.BRIGHT_RED), file=sys.stderr)
            return 1

    elif sub == "decide":
        try:
            dec_id = args.decision_id
            choice = args.option
            opt_idx = int(choice) - 1 if choice.isdigit() else None
            comment = choice if not choice.isdigit() else None
            res = client.decision_answer(decision_id=dec_id, option_index=opt_idx, comment=comment)
            print(colorize(f"✓ Decision answered: {res}", Colors.BRIGHT_GREEN))
            return 0
        except Exception as exc:
            print(colorize(f"Error submitting decision: {exc}", Colors.BRIGHT_RED), file=sys.stderr)
            return 1

    elif sub == "chat":
        msg_text = " ".join(args.message).strip()
        if not msg_text:
            print("Error: Empty chat message.", file=sys.stderr)
            return 1
        return asyncio.run(_run_stream_chat(config, msg_text))

    elif sub == "run":
        prompt_text = " ".join(args.prompt).strip()
        if not prompt_text:
            print("Error: Empty prompt.", file=sys.stderr)
            return 1
        try:
            created = client.task_create(
                description=prompt_text,
                workspace=args.workspace,
                project_id=config.project_id,
            )
            task_id = created.get("task_id") or ""
            print(colorize(f"✓ Task created: {task_id}", Colors.BRIGHT_GREEN, bold=True))
            return asyncio.run(_watch_task(config, client, task_id))
        except Exception as exc:
            print(colorize(f"Error running task: {exc}", Colors.BRIGHT_RED), file=sys.stderr)
            return 1

    elif sub == "repl":
        repl = OuroborosREPL(config)
        asyncio.run(repl.run())
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
