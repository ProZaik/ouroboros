"""Slash command dispatcher for Ouroboros CLI."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from ouroboros_cli.commands.handlers import (
    handle_cancel,
    handle_clear,
    handle_compact,
    handle_decision,
    handle_diff,
    handle_evolve,
    handle_health,
    handle_help,
    handle_history,
    handle_hurry,
    handle_logs,
    handle_memory,
    handle_mode,
    handle_model,
    handle_models,
    handle_projects,
    handle_review,
    handle_session,
    handle_status,
    handle_task,
    handle_tasks,
)
from ouroboros_cli.models.state import SessionState
from ouroboros_cli.transport.client import OuroborosHTTPClient
from ouroboros_cli.transport.websocket import OuroborosWSClient
from ouroboros_cli.ui.ansi import Colors, colorize

CommandHandler = Callable[[List[str], SessionState, OuroborosHTTPClient, Optional[OuroborosWSClient]], str]


class CommandDispatcher:
    """Dispatches slash commands to their respective handler functions."""

    def __init__(self):
        self._handlers: Dict[str, CommandHandler] = {}
        self._register_default_commands()

    def register(self, command_name: str, handler: CommandHandler) -> None:
        cmd = command_name.lower()
        if not cmd.startswith("/"):
            cmd = "/" + cmd
        self._handlers[cmd] = handler

    def _register_default_commands(self) -> None:
        self.register("/help", handle_help)
        self.register("/status", handle_status)
        self.register("/tasks", handle_tasks)
        self.register("/task", handle_task)
        self.register("/projects", handle_projects)
        self.register("/project", handle_projects)
        self.register("/cancel", handle_cancel)
        self.register("/abort", handle_cancel)
        self.register("/hurry", handle_hurry)
        self.register("/decision", handle_decision)
        self.register("/mode", handle_mode)
        self.register("/model", handle_model)
        self.register("/models", handle_models)
        self.register("/evolve", handle_evolve)
        self.register("/campaign", handle_evolve)
        self.register("/memory", handle_memory)
        self.register("/scratchpad", handle_memory)
        self.register("/diff", handle_diff)
        self.register("/review", handle_review)
        self.register("/compact", handle_compact)
        self.register("/history", handle_history)
        self.register("/logs", handle_logs)
        self.register("/health", handle_health)
        self.register("/session", handle_session)
        self.register("/clear", handle_clear)

    def is_command(self, text: str) -> bool:
        return text.strip().startswith("/")

    def dispatch(
        self,
        text: str,
        state: SessionState,
        http_client: OuroborosHTTPClient,
        ws_client: Optional[OuroborosWSClient] = None,
    ) -> Tuple[bool, str]:
        """Dispatch a slash command.

        Returns (should_exit, output_message).
        """
        parts = text.strip().split()
        if not parts:
            return False, ""

        cmd = parts[0].lower()
        args = parts[1:]

        if cmd in ("/quit", "/exit", "/q"):
            return True, colorize("Goodbye!", Colors.BRIGHT_CYAN)

        handler = self._handlers.get(cmd)
        if handler:
            result = handler(args, state, http_client, ws_client)
            return False, result

        return False, colorize(f"Unknown command '{cmd}'. Type /help for available commands.", Colors.BRIGHT_RED)
