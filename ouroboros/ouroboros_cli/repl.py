"""Interactive streaming REPL engine for Ouroboros CLI."""

from __future__ import annotations

import asyncio
import sys
from typing import Optional

from prompt_toolkit.patch_stdout import patch_stdout

from ouroboros_cli.commands.dispatcher import CommandDispatcher
from ouroboros_cli.config import CLIConfig
from ouroboros_cli.models.contracts import ChatMessage, LogEvent, QuizItem
from ouroboros_cli.models.state import SessionState
from ouroboros_cli.transport.client import OuroborosHTTPClient
from ouroboros_cli.transport.websocket import OuroborosWSClient
from ouroboros_cli.ui.ansi import Colors, Style, colorize, cprint
from ouroboros_cli.ui.prompt import create_prompt_session
from ouroboros_cli.ui.widgets import (
    render_chat_message,
    render_decision_card,
    render_status_banner,
    render_tool_event,
)


class OuroborosREPL:
    """Interactive streaming REPL session."""

    def __init__(self, config: CLIConfig):
        self.config = config
        self.state = SessionState(chat_id=config.chat_id, project_id=config.project_id)
        self.http_client = OuroborosHTTPClient(base_url=config.http_base_url, timeout=config.timeout)
        self.ws_client = OuroborosWSClient(
            url=config.ws_url,
            initial_retry_delay=config.ws_reconnect_initial_delay,
            max_retry_delay=config.ws_reconnect_max_delay,
        )
        self.dispatcher = CommandDispatcher()
        self.prompt_session = create_prompt_session()
        self._running = False
        self._setup_ws_listeners()

    def _setup_ws_listeners(self) -> None:
        """Register handlers for all daemon WebSocket events."""

        def on_open(data):
            self.state.connected = True
            cprint(colorize(f"✓ Connected to Ouroboros daemon at {self.config.ws_url}", Colors.BRIGHT_GREEN, bold=True))

        def on_disconnect(data):
            self.state.set_disconnected()
            cprint(colorize(f"⚠ Disconnected from Ouroboros daemon. Reconnecting in background...", Colors.BRIGHT_YELLOW))

        def on_heartbeat(data):
            self.state.update_heartbeat()

        def on_chat(data):
            msg = ChatMessage.from_dict(data)
            # Filter messages intended for this thread or global
            if msg.chat_id and msg.chat_id != self.state.chat_id:
                return

            self.state.add_message(msg)

            # Skip echoing the user's own prompt which was already printed
            if msg.role == "user" and msg.sender_session_id == self.ws_client.session_id:
                return

            if not msg.content.strip():
                return

            rendered = render_chat_message(msg, render_md=self.config.render_markdown)
            cprint(rendered)

        def on_log(data):
            event = LogEvent.from_dict(data)
            if event.tool:
                self.state.update_tool_status(event.tool, event.message or event.event)
            # Print prominent tool activity
            if event.tool or event.level in ("warning", "error"):
                line = render_tool_event(event)
                cprint(line)

        def on_quiz(data):
            quiz = QuizItem.from_dict(data)
            self.state.set_quiz(quiz)
            card = render_decision_card(quiz)
            cprint("\n" + card + "\n")

        def on_quiz_state(data):
            quiz_id = str(data.get("quiz_id") or "")
            state_str = str(data.get("state") or data.get("quiz_state") or "")
            if state_str == "answered":
                self.state.resolve_quiz(quiz_id)
                cprint(colorize(f"✓ Decision {quiz_id} recorded as answered.", Colors.BRIGHT_GREEN))

        def on_typing(data):
            self.state.is_thinking = True

        self.ws_client.on("open", on_open)
        self.ws_client.on("disconnect", on_disconnect)
        self.ws_client.on("heartbeat", on_heartbeat)
        self.ws_client.on("chat", on_chat)
        self.ws_client.on("log", on_log)
        self.ws_client.on("quiz", on_quiz)
        self.ws_client.on("quiz_state", on_quiz_state)
        self.ws_client.on("typing", on_typing)

    async def run(self) -> None:
        """Run the REPL loop."""
        self._running = True

        # Print welcome banner
        cprint(colorize("╔══════════════════════════════════════════════════════════════╗", Colors.BRIGHT_CYAN))
        cprint(colorize("║              OUROBOROS AUTONOMOUS AGENT REPL                ║", Colors.BRIGHT_CYAN, bold=True))
        cprint(colorize("║           Full Web UI Parity Streaming Terminal             ║", Colors.BRIGHT_CYAN))
        cprint(colorize("╚══════════════════════════════════════════════════════════════╝", Colors.BRIGHT_CYAN))
        cprint(colorize("Connecting to daemon...", Colors.GRAY))

        # Check initial daemon state via HTTP
        try:
            d_state = self.http_client.state()
            self.state.daemon_state = d_state
            banner = render_status_banner(d_state, self.config.host, self.config.port)
            cprint(banner)
        except Exception as exc:
            cprint(colorize(f"Warning: Could not fetch initial state: {exc}", Colors.BRIGHT_YELLOW))

        # Start WebSocket client in background
        await self.ws_client.start()

        # Brief pause to allow initial WS connection
        await asyncio.sleep(0.5)

        cprint(colorize("Ready! Type your message or /help for commands. Press Ctrl+D to exit.\n", Colors.GRAY))

        # Main interactive loop with patch_stdout
        with patch_stdout():
            while self._running:
                try:
                    mode_str = self.state.daemon_state.runtime_mode or "ouroboros"
                    proj_str = f" @{self.state.project_id}" if self.state.project_id else ""
                    prompt_text = [
                        ("class:prompt", "ouroboros"),
                        ("class:mode", f" [{mode_str}{proj_str}]"),
                        ("class:indicator", " ❯ "),
                    ]

                    user_input = await self.prompt_session.prompt_async(prompt_text)
                    text = user_input.strip()

                    if not text:
                        continue

                    # Check for slash commands
                    if self.dispatcher.is_command(text):
                        should_exit, output = self.dispatcher.dispatch(
                            text,
                            self.state,
                            self.http_client,
                            self.ws_client,
                        )
                        if output:
                            cprint(output)
                        if should_exit:
                            break
                        continue

                    # Check for quick numeric decision answer if a quiz is currently open
                    open_quiz = self.state.get_latest_open_quiz()
                    if open_quiz and text.isdigit() and 1 <= int(text) <= len(open_quiz.options):
                        opt_idx = int(text) - 1
                        try:
                            res = self.http_client.decision_answer(
                                decision_id=open_quiz.decision_id,
                                option_index=opt_idx,
                            )
                            self.state.resolve_quiz(open_quiz.quiz_id, answered_index=opt_idx)
                            cprint(colorize(f"✓ Answered Option {text}: {open_quiz.options[opt_idx].text}", Colors.BRIGHT_GREEN, bold=True))
                            continue
                        except Exception as exc:
                            cprint(colorize(f"Error answering decision: {exc}", Colors.BRIGHT_RED))
                            continue

                    # Otherwise, send as chat prompt
                    cprint(colorize("❯ Sending...", Colors.GRAY))
                    try:
                        await self.ws_client.send_chat(
                            content=text,
                            chat_id=self.state.chat_id,
                            project_id=self.state.project_id,
                        )
                    except Exception as exc:
                        cprint(colorize(f"Failed to send message: {exc}", Colors.BRIGHT_RED))

                except (KeyboardInterrupt, asyncio.CancelledError):
                    cprint(colorize("\n(Cancelled input. Use /quit or Ctrl+D to exit)", Colors.GRAY))
                except EOFError:
                    cprint(colorize("\nExiting Ouroboros REPL. Goodbye!", Colors.BRIGHT_CYAN))
                    break

        await self.ws_client.stop()
