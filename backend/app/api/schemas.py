from typing import Any, Literal

from pydantic import BaseModel


AgentStepName = Literal["planning", "tool_selection", "tool_execution", "validation", "final_answer"]


class ChatRequest(BaseModel):
    message: str
    model: str | None = None


class ChatResponse(BaseModel):
    answer: str


class AgentStep(BaseModel):
    step: AgentStepName
    label: str
    description: str
    status: str
    agent: str | None = None
    tool: str | None = None
    metadata: dict[str, Any] | None = None


class PlannerResult(BaseModel):
    intent: Literal["chat", "k8s", "file", "code", "tool", "unknown"]
    confidence: float
    reason: str
    suggested_tool: str | None = None
    needs_tool: bool


class ToolInfo(BaseModel):
    name: str
    category: str
    description: str
    status: str
    detail: str
