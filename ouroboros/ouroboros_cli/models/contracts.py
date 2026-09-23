"""Domain contracts and typed structures matching Ouroboros Daemon API."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ChatMessage:
    role: str  # 'user', 'assistant', 'system'
    content: str
    markdown: bool = True
    task_id: str = ""
    is_progress: bool = False
    system_type: str = ""
    ts: str = ""
    chat_id: int = 1
    project_id: str = ""
    client_message_id: str = ""
    sender_session_id: str = ""
    source: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ChatMessage:
        content = str(data.get("content") or data.get("text") or "")
        if not content and data.get("system_type") == "task_summary" and isinstance(data.get("historical_terminal"), dict):
            term = data["historical_terminal"]
            tid = data.get("task_id", "")
            content = f"Task {tid} settled: {term.get('status', 'finished')}"

        return cls(
            role=str(data.get("role") or "assistant"),
            content=content,
            markdown=bool(data.get("markdown", True)),
            task_id=str(data.get("task_id") or ""),
            is_progress=bool(data.get("is_progress", False)),
            system_type=str(data.get("system_type") or ""),
            ts=str(data.get("ts") or ""),
            chat_id=int(data.get("chat_id") or 1) if data.get("chat_id") is not None else 1,
            project_id=str(data.get("project_id") or ""),
            client_message_id=str(data.get("client_message_id") or ""),
            sender_session_id=str(data.get("sender_session_id") or ""),
            source=str(data.get("source") or ""),
            raw=data,
        )


@dataclass
class QuizOption:
    index: int
    text: str

    @classmethod
    def from_item(cls, index: int, item: Any) -> QuizOption:
        if isinstance(item, dict):
            text = str(item.get("text") or item.get("label") or item.get("title") or "")
        else:
            text = str(item)
        return cls(index=index, text=text)


@dataclass
class QuizItem:
    quiz_id: str
    task_id: str
    question: str
    options: List[QuizOption]
    stake: str = ""
    assumption: str = ""
    wait_for_answer: bool = False
    state: str = "open"  # 'open', 'answered', 'expired_terminal'
    answered_index: Optional[int] = None
    comment: Optional[str] = None
    ts: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> QuizItem:
        raw_options = data.get("options") or []
        options = [
            QuizOption.from_item(i, opt)
            for i, opt in enumerate(raw_options)
        ]
        return cls(
            quiz_id=str(data.get("quiz_id") or ""),
            task_id=str(data.get("task_id") or ""),
            question=str(data.get("question") or ""),
            options=options,
            stake=str(data.get("stake") or ""),
            assumption=str(data.get("assumption") or ""),
            wait_for_answer=bool(data.get("wait_for_answer", False)),
            state=str(data.get("state") or data.get("quiz_state") or "open"),
            answered_index=data.get("answered_index") if isinstance(data.get("answered_index"), int) else None,
            comment=str(data.get("comment")) if data.get("comment") is not None else None,
            ts=str(data.get("ts") or ""),
            raw=data,
        )

    @property
    def decision_id(self) -> str:
        return f"quiz:{self.task_id}:{self.quiz_id}"


@dataclass
class LogEvent:
    level: str  # 'info', 'warning', 'error', 'debug'
    message: str
    tool: str = ""
    event: str = ""
    task_id: str = ""
    ts: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> LogEvent:
        payload = data.get("data") if isinstance(data.get("data"), dict) else data
        return cls(
            level=str(payload.get("level") or "info").lower(),
            message=str(payload.get("message") or payload.get("content") or ""),
            tool=str(payload.get("tool") or payload.get("tool_name") or ""),
            event=str(payload.get("event") or payload.get("action") or ""),
            task_id=str(payload.get("task_id") or ""),
            ts=str(payload.get("ts") or data.get("ts") or ""),
            raw=data,
        )


@dataclass
class TaskSummary:
    id: str
    status: str  # 'running', 'pending', 'completed', 'failed'
    objective: str
    created_at: str = ""
    runtime_sec: float = 0.0
    priority: int = 0
    worker_id: Optional[int] = None
    suggested_name: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any], default_status: str = "running") -> TaskSummary:
        task_data = data.get("task") if isinstance(data.get("task"), dict) else data
        task_id = str(
            data.get("task_id")
            or data.get("id")
            or task_data.get("task_id")
            or task_data.get("id")
            or ""
        )
        contract = task_data.get("task_contract") if isinstance(task_data.get("task_contract"), dict) else {}
        narrative = task_data.get("continuation_narrative") if isinstance(task_data.get("continuation_narrative"), dict) else {}
        raw_obj = (
            task_data.get("objective")
            or task_data.get("origin_message_text")
            or contract.get("objective")
            or task_data.get("title")
            or task_data.get("description")
            or task_data.get("text")
            or (narrative.get("text", "")[:120] if isinstance(narrative.get("text"), str) else "")
            or task_data.get("result")
            or ""
        )
        obj = str(raw_obj).strip()

        st = str(task_data.get("started_at") or data.get("started_at") or "")
        en = str(task_data.get("updated_at") or data.get("updated_at") or task_data.get("ts") or data.get("ts") or "")
        sec = float(data.get("runtime_sec") or task_data.get("runtime_sec") or 0.0)
        status_val = str(data.get("status") or task_data.get("status") or default_status)

        if sec == 0.0 and st:
            try:
                t1 = datetime.datetime.fromisoformat(st)
                if en and status_val.lower() in ("completed", "failed", "cancelled", "canceled"):
                    t2 = datetime.datetime.fromisoformat(en)
                else:
                    t2 = datetime.datetime.now(datetime.timezone.utc)
                sec = max(0.0, (t2 - t1).total_seconds())
            except Exception:
                pass

        created = str(
            task_data.get("created_at")
            or data.get("created_at")
            or task_data.get("started_at")
            or data.get("started_at")
            or task_data.get("ts")
            or data.get("ts")
            or ""
        )

        return cls(
            id=task_id,
            status=status_val,
            objective=obj,
            created_at=created,
            runtime_sec=sec,
            priority=int(data.get("priority") or task_data.get("priority") or 0),
            worker_id=data.get("worker_id") or task_data.get("worker_id"),
            suggested_name=str(task_data.get("suggested_name") or ""),
        )


@dataclass
class DaemonState:
    uptime: int = 0
    workers_alive: int = 0
    workers_total: int = 0
    pending_count: int = 0
    running_count: int = 0
    spent_usd: float = 0.0
    budget_limit: float = 0.0
    branch: str = ""
    sha: str = ""
    runtime_mode: str = ""
    context_mode: str = ""
    safety_mode: str = ""
    model: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DaemonState:
        acct = data.get("accounting") if isinstance(data.get("accounting"), dict) else {}
        spent = float(data.get("spent_usd") or acct.get("settled_usd") or acct.get("accounted_usd") or 0.0)
        budget = float(data.get("budget_limit") or acct.get("limit_usd") or 0.0)

        return cls(
            uptime=int(data.get("uptime") or 0),
            workers_alive=int(data.get("workers_alive") or 0),
            workers_total=int(data.get("workers_total") or 0),
            pending_count=int(data.get("pending_count") or 0),
            running_count=int(data.get("running_count") or 0),
            spent_usd=spent,
            budget_limit=budget,
            branch=str(data.get("branch") or ""),
            sha=str(data.get("sha") or ""),
            runtime_mode=str(data.get("runtime_mode") or ""),
            context_mode=str(data.get("context_mode") or ""),
            safety_mode=str(data.get("safety_mode") or ""),
            model=str(data.get("model") or ""),
        )
