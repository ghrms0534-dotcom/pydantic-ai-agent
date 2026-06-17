from backend.app.agent.spawn import spawn_agent
from backend.app.api.schemas import PlannerResult


def test_spawn_selects_registered_agents() -> None:
    for target, display_name in {
        "chat": "Chat Agent",
        "git": "Git Agent",
        "github": "GitHub Agent",
        "kubernetes": "Kubernetes Agent",
        "docker": "Docker Agent",
    }.items():
        spawned = spawn_agent(target, _plan(target), None)

        assert spawned.name == target
        assert spawned.display_name == display_name
        assert spawned.fallback_used is False


def test_spawn_unknown_agent_falls_back_to_chat() -> None:
    spawned = spawn_agent("missing", _plan("missing"), None)

    assert spawned.name == "chat"
    assert spawned.display_name == "Chat Agent"
    assert spawned.fallback_used is True


def _plan(target_agent: str) -> PlannerResult:
    return PlannerResult(
        intent=f"{target_agent}_intent",
        confidence=0.5,
        reason="test",
        needs_tool=False,
        target_agent=target_agent,
    )
