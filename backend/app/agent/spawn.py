from dataclasses import dataclass
from typing import Any

from backend.app.agent import memory, tools
from backend.app.api.schemas import PlannerResult


FALLBACK_AGENT = "chat"


@dataclass(frozen=True)
class SpawnedAgent:
    name: str
    display_name: str
    description: str
    capabilities: list[str]
    tools: list[str]
    enabled: bool
    fallback_used: bool = False


def list_agent_registry() -> list[dict[str, Any]]:
    return tools.list_agents()


def spawn_agent(target_agent: str, planner_result: PlannerResult, session_id: str | None) -> SpawnedAgent:
    _save_trace(session_id, "agent_spawn_requested", target_agent, planner_result.model_dump_json())
    agents = {agent["name"]: agent for agent in list_agent_registry()}
    agent = agents.get(target_agent)

    if agent and agent.get("enabled", True):
        spawned = _spawned(agent)
        _save_trace(session_id, "agent_spawned", target_agent, spawned.display_name)
        return spawned

    fallback = _spawned(agents[FALLBACK_AGENT], fallback_used=True)
    step = "agent_spawn_fallback_used" if agent is None or not agent.get("enabled", False) else "agent_spawn_failed"
    _save_trace(session_id, step, target_agent, fallback.display_name)
    return fallback


def _spawned(agent: dict[str, Any], fallback_used: bool = False) -> SpawnedAgent:
    return SpawnedAgent(
        name=str(agent["name"]),
        display_name=str(agent["display_name"]),
        description=str(agent["description"]),
        capabilities=list(agent.get("capabilities", [])),
        tools=list(agent.get("tools", [])),
        enabled=bool(agent.get("enabled", True)),
        fallback_used=fallback_used,
    )


def _save_trace(session_id: str | None, step: str, input_text: str, output_text: str) -> None:
    if session_id is not None:
        memory.save_agent_trace(session_id, "Orchestrator Agent", step, input_text, output_text)
