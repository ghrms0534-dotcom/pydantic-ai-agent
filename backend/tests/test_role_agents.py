import pytest

from backend.app.agent import role_agents
from backend.app.agent.planner import plan_message
from backend.app.config import get_settings


@pytest.mark.asyncio
async def test_tool_agent_falls_back_to_ollama_model_when_selected_model_fails(monkeypatch) -> None:
    monkeypatch.setenv("FAST_MODEL", "missing:model")
    monkeypatch.setenv("OLLAMA_MODEL", "fallback:model")
    get_settings.cache_clear()
    calls: list[str | None] = []

    async def fake_run_agent(message: str, model_name: str | None = None) -> str:
        calls.append(model_name)
        if model_name == "missing:model":
            raise RuntimeError("model not found")
        return "fallback answer"

    monkeypatch.setattr(role_agents.runner, "run_agent", fake_run_agent)

    result = await role_agents.run_role_agent_flow("안녕", plan_message("안녕"), None)

    assert result.answer == "fallback answer"
    assert calls == ["missing:model", None]

    get_settings.cache_clear()
