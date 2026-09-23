"""Configuration settings and environment variable resolution for Ouroboros CLI."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class CLIConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    timeout: float = 30.0
    ws_reconnect_initial_delay: float = 1.0
    ws_reconnect_max_delay: float = 15.0
    chat_id: int = 1
    project_id: str = ""
    render_markdown: bool = True
    color: bool = True
    debug: bool = False

    @property
    def http_base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def ws_url(self) -> str:
        return f"ws://{self.host}:{self.port}/ws"

    @classmethod
    def from_env(
        cls,
        host: Optional[str] = None,
        port: Optional[int] = None,
        chat_id: Optional[int] = None,
        project_id: Optional[str] = None,
    ) -> CLIConfig:
        env_host = host or os.environ.get("OUROBOROS_SERVER_HOST") or "127.0.0.1"
        raw_port = port or os.environ.get("OUROBOROS_SERVER_PORT") or "8765"
        try:
            env_port = int(raw_port)
        except (ValueError, TypeError):
            env_port = 8765

        # Check for full URL override
        full_url = os.environ.get("OUROBOROS_SERVER_URL", "")
        if full_url:
            import urllib.parse
            parsed = urllib.parse.urlparse(full_url)
            if parsed.hostname:
                env_host = parsed.hostname
            if parsed.port:
                env_port = parsed.port

        env_chat = chat_id
        if env_chat is None:
            raw_chat = os.environ.get("OUROBOROS_CLI_CHAT_ID", "1")
            try:
                env_chat = int(raw_chat)
            except ValueError:
                env_chat = 1

        env_proj = project_id if project_id is not None else os.environ.get("OUROBOROS_CLI_PROJECT_ID", "")

        return cls(
            host=env_host,
            port=env_port,
            chat_id=env_chat,
            project_id=env_proj,
            debug=os.environ.get("OUROBOROS_CLI_DEBUG", "").lower() in ("1", "true", "yes"),
        )
