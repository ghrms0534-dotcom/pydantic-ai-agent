from typing import Literal

from backend.app.config import get_settings


TaskType = Literal["planning", "selection", "execution", "validation", "summary"]


def select_model(intent: str, agent: str, task_type: TaskType) -> str:
    settings = get_settings()
    fallback = settings.ollama_model
    fast_model = settings.fast_model or fallback
    korean_model = settings.korean_model or fallback
    reasoning_model = settings.reasoning_model or fallback

    if task_type in {"planning", "validation"}:
        return reasoning_model
    if task_type == "summary" or agent == "Summary Agent":
        return korean_model
    if agent == "Chat Agent" and intent == "chat":
        return fast_model
    if agent in {"DevOps Agent", "Tool Agent"}:
        return fast_model
    return fallback
