"""HTTP REST client for Ouroboros Daemon API."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Dict, List, Optional

from ouroboros_cli.models.contracts import DaemonState, TaskSummary


class APIError(Exception):
    """Raised when an API endpoint returns an error HTTP status."""

    def __init__(self, message: str, status_code: int = 500, payload: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


class ConnectionError(Exception):
    """Raised when the daemon cannot be reached or times out."""
    pass


class OuroborosHTTPClient:
    """Synchronous REST client for Ouroboros daemon."""

    def __init__(self, base_url: str = "http://127.0.0.1:8765", timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        url = self.base_url + path
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
        to = timeout if timeout is not None else self.timeout

        try:
            with urllib.request.urlopen(req, timeout=to) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            err_payload: Dict[str, Any] = {}
            try:
                err_payload = json.loads(raw)
                msg = err_payload.get("error") or raw
            except Exception:
                msg = raw or str(exc)
            raise APIError(f"HTTP {exc.code}: {msg}", status_code=exc.code, payload=err_payload) from exc
        except urllib.error.URLError as exc:
            raise ConnectionError(f"Failed to connect to Ouroboros daemon at {self.base_url}: {exc}") from exc
        except TimeoutError as exc:
            raise ConnectionError(f"Request to Ouroboros daemon timed out at {self.base_url}") from exc

        if not raw.strip():
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    # --- Core Health & State Endpoints ---

    def health(self) -> Dict[str, Any]:
        return self.request("GET", "/api/health")

    def state(self) -> DaemonState:
        data = self.request("GET", "/api/state")
        return DaemonState.from_dict(data)

    def is_alive(self) -> bool:
        try:
            res = self.health()
            return res.get("status") == "ok"
        except Exception:
            return False

    # --- Tasks Endpoints ---

    def tasks_list(self, limit: int = 50) -> Dict[str, List[TaskSummary]]:
        data = self.request("GET", f"/api/tasks?limit={limit}")
        result: Dict[str, List[TaskSummary]] = {
            "all": [],
            "running": [],
            "pending": [],
            "completed": [],
            "failed": [],
            "cancelled": [],
        }
        tasks_data = data.get("tasks") or {}
        if isinstance(tasks_data, dict):
            for item in tasks_data.get("running") or []:
                t = TaskSummary.from_dict(item, default_status="running")
                result["all"].append(t)
                result["running"].append(t)
            for item in tasks_data.get("pending") or []:
                t = TaskSummary.from_dict(item, default_status="pending")
                result["all"].append(t)
                result["pending"].append(t)
        elif isinstance(tasks_data, list):
            for item in tasks_data:
                t = TaskSummary.from_dict(item)
                result["all"].append(t)
                st = t.status.lower()
                if st in result:
                    result[st].append(t)
                elif st in ("cancelled", "canceled"):
                    result["cancelled"].append(t)
                else:
                    result.setdefault(st, []).append(t)
        return result

    def task_get(self, task_id: str) -> Dict[str, Any]:
        return self.request("GET", f"/api/tasks/{urllib.parse.quote(task_id)}")

    def task_create(
        self,
        description: str,
        title: str = "",
        workspace: str = "",
        project_id: str = "",
        timeout_sec: float = 0.0,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "description": description,
            "title": title,
            "workspace_root": workspace,
            "workspace_mode": "external" if workspace else "",
            "project_id": project_id,
            "source": "cli",
            "metadata": {
                "source": "cli",
                "client_surface": {"channel": "cli"},
            },
        }
        if timeout_sec > 0:
            body["timeout_sec"] = timeout_sec
        return self.request("POST", "/api/tasks", body)

    def task_cancel(self, task_id: str) -> Dict[str, Any]:
        return self.request("POST", f"/api/tasks/{urllib.parse.quote(task_id)}/cancel")

    def task_hurry(self, task_id: str) -> Dict[str, Any]:
        return self.request("POST", f"/api/tasks/{urllib.parse.quote(task_id)}/hurry")

    # --- Decision Endpoint ---

    def decision_answer(
        self,
        decision_id: str,
        option_index: Optional[int] = None,
        comment: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Answer an owner decision (quiz or routing) matching POST /api/decisions schema."""
        req_id = request_id or str(uuid.uuid4())
        body: Dict[str, Any] = {
            "request_id": req_id,
            "decision_id": decision_id,
        }
        if option_index is not None:
            body["option_index"] = option_index
        if comment:
            body["comment"] = comment

        return self.request("POST", "/api/decisions", body)

    # --- Settings & Mode Endpoints ---

    def settings_get(self) -> Dict[str, Any]:
        return self.request("GET", "/api/settings")

    def settings_post(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        return self.request("POST", "/api/settings", updates)

    def owner_runtime_mode(self, mode: str) -> Dict[str, Any]:
        return self.request("POST", "/api/owner/runtime-mode", {"mode": mode})

    def owner_context_mode(self, mode: str) -> Dict[str, Any]:
        return self.request("POST", "/api/owner/context-mode", {"mode": mode})

    def owner_safety_mode(self, mode: str) -> Dict[str, Any]:
        return self.request("POST", "/api/owner/safety-mode", {"mode": mode})

    def model_catalog(self) -> Dict[str, Any]:
        return self.request("GET", "/api/model-catalog")

    # --- Projects Endpoints ---

    def projects_list(self) -> List[Dict[str, Any]]:
        data = self.request("GET", "/api/projects")
        if isinstance(data, dict):
            return data.get("projects") or []
        if isinstance(data, list):
            return data
        return []

    # --- Chat & History Endpoints ---

    def chat_history(self, limit: int = 50, chat_id: int = 1, include_progress: bool = False) -> List[Dict[str, Any]]:
        n_prog = limit if include_progress else 0
        query = f"?n_human={limit}&n_progress={n_prog}&chat_id={chat_id}"
        data = self.request("GET", f"/api/chat/history{query}")
        if isinstance(data, dict):
            return data.get("messages") or data.get("history") or []
        if isinstance(data, list):
            return data
        return []

    def command_send(self, cmd: str) -> Dict[str, Any]:
        return self.request("POST", "/api/command", {"cmd": cmd})

    def logs_tail(self, name: str, limit: int = 50, task_id: str = "") -> Dict[str, Any]:
        query = f"?limit={limit}"
        if task_id:
            query += f"&task_id={urllib.parse.quote(task_id)}"
        return self.request("GET", f"/api/logs/{urllib.parse.quote(name)}{query}")
