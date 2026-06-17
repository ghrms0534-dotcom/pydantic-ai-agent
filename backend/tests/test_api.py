import json

from os import environ
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import queue as task_queue
from backend.app.agent import memory, observability, parallel, planner, runner, tools
from backend.app.api.main import app
from backend.app.config import get_settings
from backend.app.tools import registry


client = TestClient(app)
POD_OUTPUT = "NAMESPACE NAME READY STATUS RESTARTS AGE\ndefault api 1/1 Running 0 1m"


@pytest.fixture(autouse=True)
def clear_default_memory(monkeypatch, request) -> None:
    test_dir = Path(environ["TEMP"]) / "maos-pytest"
    test_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(char if char.isalnum() else "_" for char in request.node.name)
    monkeypatch.setenv("MAOS_DB_PATH", str(test_dir / f"{safe_name}.db"))
    async def fail_planner(prompt: str, model_name: str | None = None) -> str:
        raise RuntimeError("planner unavailable in tests")

    monkeypatch.setattr(planner, "run_local_agent", fail_planner)
    memory.clear_all_memory()
    observability.clear_all()


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

    assert response.status_code == 200
    assert response.json() == {"answer": "요청 처리 중 오류가 발생했습니다. 입력이나 실행 환경을 확인해주세요."}


def test_api_chat_returns_validator_message_for_tool_failure(monkeypatch) -> None:
    monkeypatch.setattr(registry, "get_k8s_pods", lambda namespace=None: "")

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
        "memory_load",
        "tool_discovery",
        "planning",
        "planner_agent",
        "agent_message_sent",
        "tool_selection",
        "parallel_execution_decision",
        "tool_execution",
        "tool_agent",
        "validation",
        "validator_agent",
        "agent_message_sent",
        "final_answer",
        "final_answer_agent",
        "memory_save",
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
    assert _agent_by_step(events, "final_answer") == "Final Answer Agent"
    assert _metadata_by_step(events, "planning")["selected_model"] == "qwen2.5:3b"
    assert _metadata_by_step(events, "tool_selection")["selected_model"] == "qwen2.5:3b"


def test_k8s_prompt_uses_devops_tool_validator_summary_flow(monkeypatch) -> None:
    monkeypatch.setattr(registry, "get_k8s_pods", lambda namespace=None: POD_OUTPUT)

    response = client.post("/api/chat/stream", json={"message": "쿠버네티스 pod 상태 알려줘"})

    assert response.status_code == 200
    events = _events(response.text)
    assert _agent_by_step(events, "planning") == "Planner Agent"
    assert _agent_by_step(events, "tool_selection") == "Kubernetes Agent"
    assert _agent_by_step(events, "tool_execution") == "Tool Agent"
    assert _agent_by_step(events, "validation") == "Validator Agent"
    assert _agent_by_step(events, "final_answer") == "Final Answer Agent"
    assert _metadata_by_step(events, "tool_execution")["selected_model"] == "qwen2.5:3b"
    assert _metadata_by_step(events, "validation")["selected_model"] == "qwen2.5:3b"
    assert _metadata_by_step(events, "final_answer")["selected_model"] == "qwen2.5:3b"


def test_api_chat_stream_planning_trace_includes_planner_result(monkeypatch) -> None:
    monkeypatch.setattr(registry, "get_k8s_pods", lambda namespace=None: POD_OUTPUT)

    response = client.post("/api/chat/stream", json={"message": "쿠버네티스 pod 상태 알려줘"})

    assert response.status_code == 200
    events = _events(response.text)
    planning = next(event for event in events if event.get("step") == "planning")
    planner = planning["metadata"]["planner"]

    assert planner["intent"] == "kubernetes_status"
    assert planner["needs_tool"] is True
    assert planner["suggested_tool"] == "get_k8s_pods"
    assert "confidence" in planner
    assert "reason" in planner


def test_api_chat_stream_validation_trace_records_failure_reason(monkeypatch) -> None:
    monkeypatch.setattr(registry, "get_k8s_pods", lambda namespace=None: "")

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


def test_api_tools_returns_discovered_tools_and_agents() -> None:
    response = client.get("/api/tools")

    assert response.status_code == 200
    data = response.json()
    assert {"name", "display_name", "description", "category", "enabled", "source"} <= data["tools"][0].keys()
    assert [agent["display_name"] for agent in data["agents"]] == [
        "Chat Agent",
        "Git Agent",
        "GitHub Agent",
        "Kubernetes Agent",
        "Docker Agent",
        "File Agent",
        "System Agent",
    ]


def test_api_agents_returns_agent_registry() -> None:
    response = client.get("/api/agents")

    assert response.status_code == 200
    agents = response.json()["agents"]
    docker = next(agent for agent in agents if agent["name"] == "docker")

    assert {"name", "description", "capabilities", "tools", "enabled"} <= docker.keys()
    assert docker["display_name"] == "Docker Agent"


def test_task_api_returns_task_status(monkeypatch) -> None:
    monkeypatch.setattr(task_queue, "_redis_command", lambda *parts: 1)
    task_id = task_queue.enqueue_task("Chat Agent", {"message": "안녕"}, "task-session")

    response = client.get(f"/api/tasks/{task_id}")
    session = client.get("/api/tasks/session/task-session")

    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    assert session.status_code == 200
    assert session.json()["tasks"][0]["task_id"] == task_id


def test_queue_mode_enqueues_chat_task(monkeypatch) -> None:
    monkeypatch.setenv("WORKER_MODE", "queue")
    get_settings.cache_clear()
    monkeypatch.setattr(task_queue, "_redis_command", lambda *parts: 1)

    response = client.post("/api/chat", json={"message": "안녕", "session_id": "queued"})

    assert response.status_code == 200
    assert response.json()["answer"].startswith("작업이 등록되었습니다. task_id=")
    assert client.get("/api/tasks/session/queued").json()["tasks"][0]["status"] == "pending"

    get_settings.cache_clear()


def test_file_request_uses_file_tool(monkeypatch) -> None:
    monkeypatch.setattr(registry, "list_project_files", lambda: "현재 프로젝트 파일 목록입니다.\n- README.md")

    response = client.post("/api/chat", json={"message": "현재 프로젝트 파일 보여줘", "session_id": "file-flow"})
    trace = client.get("/api/observability/traces").json()["traces"][0]

    assert response.status_code == 200
    assert "README.md" in response.json()["answer"]
    assert trace["selected_agent"] == "File Agent"
    assert trace["selected_tool"] == "list_project_files"


def test_memory_request_uses_memory_tool() -> None:
    memory.save_memory(
        "memory-flow",
        user_message="안녕",
        assistant_answer="안녕하세요",
        selected_agent="Chat Agent",
        executed_tool_name=None,
        tool_result="",
    )

    response = client.post("/api/chat", json={"message": "메모리 상태 알려줘", "session_id": "memory-flow"})
    trace = client.get("/api/observability/traces").json()["traces"][0]

    assert response.status_code == 200
    assert "SQLite Memory 상태입니다." in response.json()["answer"]
    assert trace["selected_agent"] == "System Agent"
    assert trace["selected_tool"] == "get_memory_status"


def test_docker_request_uses_docker_tool(monkeypatch) -> None:
    monkeypatch.setattr(registry, "get_docker_status", lambda: "현재 Docker 실행 상태입니다.\n실행 중인 컨테이너가 없습니다.")

    response = client.post("/api/chat", json={"message": "Docker 상태 알려줘", "session_id": "docker-flow"})
    trace = client.get("/api/observability/traces").json()["traces"][0]

    assert response.status_code == 200
    assert "Docker 실행 상태" in response.json()["answer"]
    assert trace["selected_agent"] == "Docker Agent"
    assert trace["selected_tool"] == "get_docker_status"


def test_git_request_uses_git_tool(monkeypatch) -> None:
    monkeypatch.setattr(registry, "get_git_status", lambda: "Git 상태 요약입니다.\n- 수정된 파일: 1개\n- 커밋되지 않은 변경사항 있음")

    response = client.post("/api/chat", json={"message": "Git 상태 알려줘", "session_id": "git-flow"})
    trace = client.get("/api/observability/traces").json()["traces"][0]

    assert response.status_code == 200
    assert "Git 상태 요약" in response.json()["answer"]
    assert trace["selected_agent"] == "Git Agent"
    assert trace["selected_tool"] == "get_git_status"


def test_api_chat_stores_and_loads_session_memory(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_run_agent(message: str, model_name: str | None = None) -> str:
        calls.append(message)
        return "blue" if len(calls) == 1 else "you said blue"

    monkeypatch.setattr(runner, "run_agent", fake_run_agent)

    first = client.post("/api/chat", json={"message": "내 색은 blue야", "session_id": "s1"})
    second = client.post("/api/chat", json={"message": "내 색 뭐였지?", "session_id": "s1"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert calls[0] == "내 색은 blue야"
    assert "Recent session memory" in calls[1]
    assert "blue" in calls[1]


def test_memory_api_get_and_delete(monkeypatch) -> None:
    async def fake_run_agent(message: str, model_name: str | None = None) -> str:
        return "stored answer"

    monkeypatch.setattr(runner, "run_agent", fake_run_agent)

    client.post("/api/chat", json={"message": "hello", "session_id": "s2"})
    response = client.get("/api/memory/s2")

    assert response.status_code == 200
    assert response.json()["memory"][0]["user_message"] == "hello"
    assert response.json()["conversations"][0]["role"] == "user"
    assert response.json()["agent_memory"][0]["agent_name"] == "Chat Agent"

    cleared = client.delete("/api/memory/s2")
    assert cleared.status_code == 200
    assert client.get("/api/memory/s2").json()["memory"] == []


def test_trace_api_returns_agent_messages(monkeypatch) -> None:
    async def fake_run_agent(message: str, model_name: str | None = None) -> str:
        return "trace answer"

    monkeypatch.setattr(runner, "run_agent", fake_run_agent)

    response = client.post("/api/chat", json={"message": "안녕", "session_id": "trace-session"})
    trace = client.get("/api/trace/trace-session")

    assert response.status_code == 200
    assert trace.status_code == 200
    assert trace.json()["trace"][0]["agent_name"] == "Planner Agent"
    assert trace.json()["trace"][0]["step"] == "planning_started"


def test_retry_retries_failed_tool_result_and_records_trace(monkeypatch) -> None:
    calls: list[str] = []

    def fake_get_k8s_pods(namespace=None) -> str:
        calls.append(namespace or "")
        return "Error: temporary failure" if len(calls) == 1 else POD_OUTPUT

    monkeypatch.setattr(registry, "get_k8s_pods", fake_get_k8s_pods)

    response = client.post("/api/chat", json={"message": "쿠버네티스 pod 상태 알려줘", "session_id": "retry"})
    trace = client.get("/api/trace/retry").json()["trace"]
    retry_steps = [item["step"] for item in trace if item["agent_name"] == "Tool Agent"]

    assert response.status_code == 200
    assert response.json()["answer"] == POD_OUTPUT
    assert len(calls) == 2
    assert "retry_attempt_1" in retry_steps
    assert "retry_validation_failed" in retry_steps
    assert "retry_attempt_2" in retry_steps
    assert "retry_success" in retry_steps


def test_observability_metrics_and_traces(monkeypatch) -> None:
    async def fake_run_agent(message: str, model_name: str | None = None) -> str:
        return POD_OUTPUT

    monkeypatch.setattr(runner, "run_agent", fake_run_agent)

    response = client.post("/api/chat", json={"message": "쿠버네티스 pod 상태 알려줘", "session_id": "obs"})
    assert response.status_code == 200

    metrics = client.get("/api/observability/metrics").json()
    assert metrics["total_requests"] == 1
    assert metrics["total_tool_calls"] == 1
    assert metrics["failed_tool_calls"] == 0
    assert metrics["last_tool_name"] == "get_k8s_pods"
    assert metrics["average_latency_ms"] >= 0

    traces = client.get("/api/observability/traces").json()["traces"]
    request_id = traces[0]["request_id"]
    trace = client.get(f"/api/observability/traces/{request_id}").json()
    assert trace["request_id"] == request_id
    assert trace["selected_agent"] == "Kubernetes Agent"
    assert trace["selected_tool"] == "get_k8s_pods"
    assert trace["tool_execution"]["status"] == "success"
    assert trace["agent_messages"][0]["from_agent"] == "Planner Agent"
    assert trace["agent_messages"][0]["to_agent"] == "Tool Agent"
    assert [step["step"] for step in trace["steps"]] == [
        "request_received",
        "memory_load",
        "tool_discovery",
        "planner_agent",
        "agent_selected",
        "agent_message_sent",
        "tool_selected",
        "parallel_execution_decision",
        "tool_execution_start",
        "tool_agent",
        "tool_execution_end",
        "agent_message_sent",
        "validation",
        "validator_agent",
        "agent_message_sent",
        "final_answer_agent",
        "memory_save",
        "final_answer",
    ]


def test_parallel_tool_execution_records_each_tool(monkeypatch) -> None:
    monkeypatch.setattr(parallel, "get_git_status", lambda: "M README.md")
    monkeypatch.setattr(parallel, "get_public_ip", lambda: "203.0.113.10")

    response = client.post("/api/chat", json={"message": "현재 git 상태랑 public ip 둘 다 알려줘", "session_id": "p"})
    assert response.status_code == 200
    assert "get_git_status" in response.json()["answer"]
    assert "get_public_ip" in response.json()["answer"]

    metrics = client.get("/api/observability/metrics").json()
    assert metrics["total_tool_calls"] == 2
    assert metrics["failed_tool_calls"] == 0

    request_id = client.get("/api/observability/traces").json()["traces"][0]["request_id"]
    trace = client.get(f"/api/observability/traces/{request_id}").json()
    steps = [step["step"] for step in trace["steps"]]

    assert "parallel_execution_decision" in steps
    assert "parallel_tool_execution_start" in steps
    assert "parallel_tool_execution_end" in steps
    assert trace["selected_tool"] == "get_git_status,get_public_ip"
    assert [item["status"] for item in trace["parallel_tool_executions"]] == ["success", "success"]


def test_general_prompt_skips_tool_agent_in_pipeline(monkeypatch) -> None:
    async def fake_run_agent(message: str, model_name: str | None = None) -> str:
        return "hello answer"

    monkeypatch.setattr(runner, "run_agent", fake_run_agent)

    response = client.post("/api/chat", json={"message": "안녕", "session_id": "general"})
    assert response.status_code == 200

    request_id = client.get("/api/observability/traces").json()["traces"][0]["request_id"]
    trace = client.get(f"/api/observability/traces/{request_id}").json()
    tool_agent = next(step for step in trace["steps"] if step["step"] == "tool_agent")

    assert tool_agent["status"] == "skipped"
    assert trace["tool_execution"] is None
    assert trace["agent_messages"][0]["to_agent"] == "Validator Agent"


def _events(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines()]


def _agent_by_step(events: list[dict], step: str) -> str:
    return next(event["agent"] for event in events if event.get("step") == step)


def _metadata_by_step(events: list[dict], step: str) -> dict:
    return next(event["metadata"] for event in events if event.get("step") == step)
