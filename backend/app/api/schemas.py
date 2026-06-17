from typing import Any, Literal

from pydantic import BaseModel


AgentStepName = Literal[
    "memory_load",
    "tool_discovery",
    "planner_agent",
    "agent_message_sent",
    "parallel_execution_decision",
    "parallel_tool_execution_start",
    "parallel_tool_execution_end",
    "planning",
    "tool_selection",
    "tool_agent",
    "tool_execution",
    "validator_agent",
    "validation",
    "final_answer_agent",
    "final_answer",
    "memory_save",
]


class ChatRequest(BaseModel):
    message: str
    model: str | None = None
    session_id: str | None = None


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
    intent: str
    confidence: float
    reason: str
    suggested_tool: str | None = None
    needs_tool: bool
    target_agent: str = "chat"
    required_tools: list[str] = []
    steps: list[str] = []
    fallback_used: bool = False


class ToolInfo(BaseModel):
    name: str
    display_name: str | None = None
    category: str
    description: str
    enabled: bool | None = None
    source: str | None = None
    status: str
    detail: str
