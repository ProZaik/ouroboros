"""Client session state management for Ouroboros CLI."""

from __future__ import annotations

import time
from typing import Dict, List, Optional

from ouroboros_cli.models.contracts import ChatMessage, DaemonState, QuizItem


class SessionState:
    """In-memory session state maintained across the REPL lifetime."""

    def __init__(self, chat_id: int = 1, project_id: str = ""):
        self.chat_id: int = chat_id
        self.project_id: str = project_id
        self.connected: bool = False
        self.last_heartbeat: float = 0.0
        self.daemon_state: DaemonState = DaemonState()
        self.active_task_id: Optional[str] = None
        self.pending_quizzes: Dict[str, QuizItem] = {}
        self.history: List[ChatMessage] = []
        self.active_tools: Dict[str, str] = {}
        self.is_thinking: bool = False

    def update_heartbeat(self) -> None:
        self.connected = True
        self.last_heartbeat = time.time()

    def set_disconnected(self) -> None:
        self.connected = False
        self.is_thinking = False

    def add_message(self, msg: ChatMessage) -> None:
        self.history.append(msg)
        if msg.task_id:
            self.active_task_id = msg.task_id
        if msg.role == "assistant" and not msg.is_progress:
            self.is_thinking = False

    def set_quiz(self, quiz: QuizItem) -> None:
        if quiz.state == "open":
            self.pending_quizzes[quiz.quiz_id] = quiz
        elif quiz.quiz_id in self.pending_quizzes:
            self.pending_quizzes[quiz.quiz_id] = quiz

    def resolve_quiz(self, quiz_id: str, answered_index: Optional[int] = None, comment: Optional[str] = None) -> Optional[QuizItem]:
        if quiz_id in self.pending_quizzes:
            quiz = self.pending_quizzes[quiz_id]
            quiz.state = "answered"
            quiz.answered_index = answered_index
            quiz.comment = comment
            return quiz
        return None

    def get_latest_open_quiz(self) -> Optional[QuizItem]:
        for quiz in reversed(list(self.pending_quizzes.values())):
            if quiz.state == "open":
                return quiz
        return None

    def set_project(self, project_id: str, chat_id: int = 1) -> None:
        self.project_id = project_id
        self.chat_id = chat_id

    def update_tool_status(self, tool_name: str, status: str) -> None:
        if status.lower() in ("done", "finished", "success", "error", "failed"):
            self.active_tools.pop(tool_name, None)
        else:
            self.active_tools[tool_name] = status
