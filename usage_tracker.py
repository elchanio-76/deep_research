from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

from agents import Usage

from new_models import SessionUsage


_CURRENT_SESSION: ContextVar[Optional[SessionUsage]] = ContextVar(
    "current_session_usage", default=None
)


def set_session_usage(session_usage: Optional[SessionUsage]) -> None:
    _CURRENT_SESSION.set(session_usage)


def get_session_usage() -> Optional[SessionUsage]:
    return _CURRENT_SESSION.get()


def record_agent_usage(agent_name: str, usage: Usage) -> None:
    session_usage = get_session_usage()
    if session_usage is None:
        return
    session_usage.add_agent_usage(agent_name, usage.input_tokens, usage.output_tokens)


def record_tool_call(agent_name: str, tool_name: str, count: int = 1) -> None:
    session_usage = get_session_usage()
    if session_usage is None:
        return
    session_usage.add_tool_call(agent_name, tool_name, count)
