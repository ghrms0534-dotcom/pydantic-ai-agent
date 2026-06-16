import json

from fastapi.testclient import TestClient

from backend.app.agent import runner, tools
from backend.app.api.main import app


client = TestClient(app)
POD_OUTPUT = "NAMESPACE NAME READY STATUS RESTARTS AGE\ndefault api 1/1 Running 0 1m"


def test_health_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_uses_agent_runner(monkeypatch) -> None:
    async def fake_run_agent(message: str, model_name: str | None = None) -> str:
        assert message == "hello"
        return "mock answer"

    monkeypatch.setattr(runner, "run_agent", fake_run_agent)

    response = client.post("/chat", json={"message": "hello"})

    assert response.status_code == 200
    assert response.json() == {"answer": "mock answer"}


def test_api_chat_uses_agent_runner(monkeypatch) -> None:
    async def fake_run_agent(message: str, model_name: str | None = None) -> str:
        assert message == "hello"
        return "mock api answer"

    monkeypatch.setattr(runner, "run_agent", fake_run_agent)

    response = client.post("/api/chat", json={"message": "hello"})

    assert response.status_code == 200
    assert response.json() == {"answer": "mock api answer"}


def test_api_chat_handles_agent_error(monkeypatch) -> None:
    async def fake_run_agent(message: str, model_name: str | None = None) -> str:
        raise RuntimeError("boom")

    monkeypatch.setattr(runner, "run_agent", fake_run_agent)

    response = client.post("/api/chat", json={"message": "hello"})

    assert response.status_code == 500
    assert response.json() == {"detail": "Agent execution failed."}


def test_api_chat_returns_validator_message_for_tool_failure(monkeypatch) -> None:
    async def fake_run_agent(message: str, model_name: str | None = None) -> str:
        return ""

    monkeypatch.setattr(runner, "run_agent", fake_run_agent)

    response = client.post("/api/chat", json={"message": "쿠버네티스 pod 상태 알려줘"})

    assert response.status_code == 200
    assert response.json() == {"answer": "결과가 비어 있습니다."}


def test_api_chat_stream_includes_agent_steps(monkeypatch) -> None:
    async def fake_run_agent(message: str, model_name: str | None = None) -> str:
        assert message == "hello"
        return "stream answer"

    monkeypatch.setattr(runner, "run_agent", fake_run_agent)

    response = client.post("/api/chat/stream", json={"message": "hello"})

    assert response.status_code == 200
    events = _events(response.text)
    trace_events = [event for event in events if event["type"] == "trace"]

    assert [event["step"] for event in trace_events] == [
        "planning",
        "tool_selection",
        "tool_execution",
        "validation",
        "final_answer",
    ]
    assert all({"label", "description", "status"} <= event.keys() for event in trace_events)
    assert events[-1] == {"type": "answer", "answer": "stream answer"}


def test_chat_prompt_uses_chat_agent_flow(monkeypatch) -> None:
    async def fake_run_agent(message: str, model_name: str | None = None) -> str:
        return "chat answer"

    monkeypatch.setattr(runner, "run_agent", fake_run_agent)

    response = client.post("/api/chat/stream", json={"message": "안녕"})

    assert response.status_code == 200
    events = _events(response.text)
    assert _agent_by_step(events, "planning") == "Planner Agent"
    assert _agent_by_step(events, "tool_selection") == "Chat Agent"
    assert _agent_by_step(events, "tool_execution") == "Tool Agent"
    assert _agent_by_step(events, "validation") == "Validator Agent"
    assert _agent_by_step(events, "final_answer") == "Summary Agent"
    assert _metadata_by_step(events, "planning")["selected_model"] == "qwen2.5:3b"
    assert _metadata_by_step(events, "tool_selection")["selected_model"] == "qwen2.5:3b"


def test_k8s_prompt_uses_devops_tool_validator_summary_flow(monkeypatch) -> None:
    async def fake_run_agent(message: str, model_name: str | None = None) -> str:
        return POD_OUTPUT

    monkeypatch.setattr(runner, "run_agent", fake_run_agent)

    response = client.post("/api/chat/stream", json={"message": "쿠버네티스 pod 상태 알려줘"})

    assert response.status_code == 200
    events = _events(response.text)
    assert _agent_by_step(events, "planning") == "Planner Agent"
    assert _agent_by_step(events, "tool_selection") == "DevOps Agent"
    assert _agent_by_step(events, "tool_execution") == "Tool Agent"
    assert _agent_by_step(events, "validation") == "Validator Agent"
    assert _agent_by_step(events, "final_answer") == "Summary Agent"
    assert _metadata_by_step(events, "tool_execution")["selected_model"] == "qwen2.5:3b"
    assert _metadata_by_step(events, "validation")["selected_model"] == "qwen2.5:3b"
    assert _metadata_by_step(events, "final_answer")["selected_model"] == "qwen2.5:3b"


def test_api_chat_stream_planning_trace_includes_planner_result(monkeypatch) -> None:
    async def fake_run_agent(message: str, model_name: str | None = None) -> str:
        return POD_OUTPUT

    monkeypatch.setattr(runner, "run_agent", fake_run_agent)

    response = client.post("/api/chat/stream", json={"message": "쿠버네티스 pod 상태 알려줘"})

    assert response.status_code == 200
    events = _events(response.text)
    planning = next(event for event in events if event.get("step") == "planning")
    planner = planning["metadata"]["planner"]

    assert planner["intent"] == "k8s"
    assert planner["needs_tool"] is True
    assert planner["suggested_tool"] == "get_k8s_pods"
    assert "confidence" in planner
    assert "reason" in planner


def test_api_chat_stream_validation_trace_records_failure_reason(monkeypatch) -> None:
    async def fake_run_agent(message: str, model_name: str | None = None) -> str:
        return ""

    monkeypatch.setattr(runner, "run_agent", fake_run_agent)

    response = client.post("/api/chat/stream", json={"message": "현재 pods 상태 알려줘"})

    assert response.status_code == 200
    events = _events(response.text)
    validation = next(event for event in events if event.get("step") == "validation")

    assert validation["agent"] == "Validator Agent"
    assert validation["status"] == "error"
    assert validation["metadata"]["reason"] == "empty"
    assert validation["metadata"]["selected_model"] == "qwen2.5:3b"
    assert events[-1] == {"type": "answer", "answer": "결과가 비어 있습니다."}


def test_tools_uses_tool_listing(monkeypatch) -> None:
    monkeypatch.setattr(
        tools,
        "list_tools",
        lambda: [{"name": "mock_tool", "category": "mock", "description": "mock"}],
    )

    response = client.get("/tools")

    assert response.status_code == 200
    assert response.json() == {
        "tools": [{"name": "mock_tool", "category": "mock", "description": "mock"}]
    }


def _events(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines()]


def _agent_by_step(events: list[dict], step: str) -> str:
    return next(event["agent"] for event in events if event.get("step") == step)


def _metadata_by_step(events: list[dict], step: str) -> dict:
    return next(event["metadata"] for event in events if event.get("step") == step)
