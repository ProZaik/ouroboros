"""Asynchronous WebSocket client for real-time streaming with Ouroboros Daemon."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Callable, Coroutine, Dict, List, Optional

import websockets
from websockets.exceptions import ConnectionClosed

log = logging.getLogger(__name__)

Listener = Callable[[Dict[str, Any]], Coroutine[Any, Any, None]] | Callable[[Dict[str, Any]], None]


class OuroborosWSClient:
    """Async WebSocket client supporting reconnection, heartbeat watchdog, and typed event dispatch."""

    def __init__(
        self,
        url: str = "ws://127.0.0.1:8765/ws",
        initial_retry_delay: float = 1.0,
        max_retry_delay: float = 15.0,
        session_id: Optional[str] = None,
    ):
        self.url = url
        self.initial_retry_delay = initial_retry_delay
        self.max_retry_delay = max_retry_delay
        self.session_id = session_id or str(uuid.uuid4())
        self._listeners: Dict[str, List[Listener]] = {}
        self._running = False
        self._connected = False
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._listen_task: Optional[asyncio.Task] = None
        self._outbound_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()

    @property
    def is_connected(self) -> bool:
        return self._connected and self._ws is not None and not self._ws.closed

    def on(self, event_type: str, handler: Listener) -> Callable[[], None]:
        """Register an event listener. Returns a disposer function."""
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(handler)

        def dispose():
            if event_type in self._listeners and handler in self._listeners[event_type]:
                self._listeners[event_type].remove(handler)

        return dispose

    async def _dispatch(self, event_type: str, data: Dict[str, Any]) -> None:
        handlers = list(self._listeners.get(event_type, [])) + list(self._listeners.get("*", []))
        for handler in handlers:
            try:
                res = handler(data)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as exc:
                log.debug("Error in event listener for %s: %s", event_type, exc)

    async def start(self) -> None:
        """Start background connection & listener loop."""
        if self._running:
            return
        self._running = True
        self._listen_task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Gracefully stop WebSocket connection."""
        self._running = False
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            self._listen_task = None
        self._connected = False
        await self._dispatch("close", {"reason": "client_shutdown"})

    async def _run_loop(self) -> None:
        delay = self.initial_retry_delay
        while self._running:
            try:
                async with websockets.connect(self.url, ping_interval=20, ping_timeout=20) as ws:
                    self._ws = ws
                    self._connected = True
                    delay = self.initial_retry_delay
                    await self._dispatch("open", {"url": self.url})

                    # Run sender and receiver concurrently
                    recv_task = asyncio.create_task(self._receiver_loop(ws))
                    send_task = asyncio.create_task(self._sender_loop(ws))

                    done, pending = await asyncio.wait(
                        [recv_task, send_task],
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for t in pending:
                        t.cancel()
                        try:
                            await t
                        except asyncio.CancelledError:
                            pass

            except (ConnectionClosed, OSError, asyncio.TimeoutError) as exc:
                self._connected = False
                self._ws = None
                await self._dispatch("disconnect", {"error": str(exc)})
            except Exception as exc:
                self._connected = False
                self._ws = None
                await self._dispatch("error", {"error": str(exc)})

            if self._running:
                await asyncio.sleep(delay)
                delay = min(delay * 1.5, self.max_retry_delay)

    async def _receiver_loop(self, ws: websockets.WebSocketClientProtocol) -> None:
        async for raw_message in ws:
            try:
                msg = json.loads(raw_message)
            except json.JSONDecodeError:
                continue
            if not isinstance(msg, dict):
                continue

            msg_type = str(msg.get("type") or "message")
            await self._dispatch(msg_type, msg)

    async def _sender_loop(self, ws: websockets.WebSocketClientProtocol) -> None:
        while self._running and not ws.closed:
            try:
                msg = await self._outbound_queue.get()
                payload = json.dumps(msg, ensure_ascii=False)
                await ws.send(payload)
                self._outbound_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception:
                break

    async def send(self, data: Dict[str, Any]) -> None:
        """Enqueue a message to send over WebSocket."""
        await self._outbound_queue.put(data)

    async def send_chat(
        self,
        content: str,
        chat_id: int = 1,
        project_id: str = "",
        force_plan: bool = False,
    ) -> str:
        """Send chat message compliant with Ouroboros ChatInbound ABI."""
        client_msg_id = str(uuid.uuid4())
        msg: Dict[str, Any] = {
            "type": "chat",
            "content": content,
            "chat_id": chat_id,
            "project_id": project_id,
            "force_plan": force_plan,
            "client_message_id": client_msg_id,
            "sender_session_id": self.session_id,
            "client_surface": {
                "channel": "cli",
                "app_version": "0.1.0",
                "client_type": "ouroboros-cli",
                "ua": "ouroboros-cli/0.1.0",
            },
        }
        await self.send(msg)
        return client_msg_id

    async def send_command(self, cmd: str) -> None:
        """Send raw command frame."""
        msg: Dict[str, Any] = {
            "type": "command",
            "cmd": cmd,
        }
        await self.send(msg)
