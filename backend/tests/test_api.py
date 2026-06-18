import json

from os import environ
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import queue as task_queue
from backend.app.agent import memory, observability, parallel, planner, runner, tools
from backend.app.api.main import app
from backend.app.config import get_settings
from backend.app.tools import local_tools, registry


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
        "Coding Agent",
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


def test_code_request_uses_coding_agent(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_run_agent(message: str, model_name: str | None = None) -> str:
        calls.append(message)
        return "코드 설명입니다."

    monkeypatch.setattr(runner, "run_agent", fake_run_agent)

    response = client.post("/api/chat", json={"message": "explain this code", "session_id": "coding-flow"})
    trace = client.get("/api/observability/traces").json()["traces"][0]

    assert response.status_code == 200
    assert response.json()["answer"] == "코드 설명입니다."
    assert trace["selected_agent"] == "Coding Agent"
    assert trace["selected_tool"] is None
    assert "You are Coding Agent" in calls[0]


def test_code_conversion_uses_coding_agent(monkeypatch) -> None:
    async def fake_run_agent(message: str, model_name: str | None = None) -> str:
        assert "Always answer in Korean" in message
        assert "Do not claim you edited files" in message
        assert "C 소스를 Java로 바꿔줘" in message
        return "Java 변환 예시입니다."

    monkeypatch.setattr(runner, "run_agent", fake_run_agent)

    response = client.post(
        "/api/chat",
        json={"message": "C 소스를 Java로 바꿔줘 int add(int a,int b){return a+b;}", "session_id": "coding-convert"},
    )
    trace = client.get("/api/observability/traces").json()["traces"][0]

    assert response.status_code == 200
    assert response.json()["answer"] == "Java 변환 예시입니다."
    assert trace["selected_agent"] == "Coding Agent"


def test_coding_agent_read_file_tool(monkeypatch) -> None:
    monkeypatch.setattr(registry, "read_file", lambda path: f"read file: {path}")

    async def fake_run_agent(message: str, model_name: str | None = None) -> str:
        assert "read_file" in message
        assert "read file: README.md" in message
        return "README.md 파일 요약입니다."

    monkeypatch.setattr(runner, "run_agent", fake_run_agent)

    response = client.post("/api/chat", json={"message": "read_file path=README.md", "session_id": "coding-read"})
    trace = client.get("/api/observability/traces").json()["traces"][0]

    assert response.status_code == 200
    assert response.json()["answer"] == "README.md 파일 요약입니다."
    assert trace["selected_agent"] == "Coding Agent"
    assert trace["selected_tool"] == "read_file"


@pytest.mark.parametrize(
    ("message", "expected_tool", "tool_output"),
    [
        ("프로젝트 구조 보여줘", "list_directory", "app/\nREADME.md"),
        ("main.py 읽어줘", "read_file", "print('hello')"),
        ("전체 코드에서 login 찾아줘", "search_code", "backend/app/auth.py: login"),
    ],
)
def test_coding_file_analysis_requests_use_read_only_tools(monkeypatch, message, expected_tool, tool_output) -> None:
    monkeypatch.setattr(registry, "list_directory", lambda path=".": tool_output)
    monkeypatch.setattr(registry, "read_file", lambda path: tool_output)
    monkeypatch.setattr(registry, "search_code", lambda keyword: tool_output)

    async def fake_run_agent(prompt: str, model_name: str | None = None) -> str:
        assert expected_tool in prompt
        assert tool_output in prompt
        return "파일 도구 결과 요약입니다."

    monkeypatch.setattr(runner, "run_agent", fake_run_agent)

    response = client.post("/api/chat", json={"message": message, "session_id": f"coding-{expected_tool}"})
    trace = client.get("/api/observability/traces").json()["traces"][0]

    assert response.status_code == 200
    assert response.json()["answer"] == "파일 도구 결과 요약입니다."
    assert trace["selected_agent"] == "Coding Agent"
    assert trace["selected_tool"] == expected_tool


def test_coding_read_only_tools_are_discovered() -> None:
    response = client.get("/api/tools")
    tool_names = {tool["name"] for tool in response.json()["tools"]}

    assert {"list_directory", "read_file", "search_code"} <= tool_names


def test_read_file_blocks_path_traversal() -> None:
    assert "root 밖" in local_tools.read_file("../pyproject.toml")


def test_read_only_file_tools_security_guards() -> None:
    assert "민감 정보" in local_tools.read_file(".env")
    assert "제외된 디렉터리" in local_tools.read_file("node_modules/package.json")
    assert "backend" in local_tools.list_directory("backend")
    assert "login" in local_tools.search_code("login")


def test_read_file_blocks_binary_file(monkeypatch) -> None:
    monkeypatch.setattr(local_tools, "_is_binary_file", lambda path: True)

    assert "읽을 수" in local_tools.read_file("pyproject.toml")


def test_coding_write_tools_modify_root_files_only(monkeypatch) -> None:
    root = Path(environ["TEMP"]) / "maos-write-tools"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(local_tools, "ROOT", root)

    result = local_tools.write_file("sample.txt", "hello")
    assert "Diff:" in result
    assert (root / "sample.txt").read_text(encoding="utf-8") == "hello"

    result = local_tools.replace_in_file("sample.txt", "hello", "hi")
    assert "+hi" in result
    assert (root / "sample.txt").read_text(encoding="utf-8") == "hi"

    assert "root" in local_tools.write_file("../outside.txt", "no")
    assert "민감 정보" in local_tools.write_file(".env", "TOKEN=x")


def test_replace_in_file_requires_exact_single_match(monkeypatch) -> None:
    root = Path(environ["TEMP"]) / "maos-write-tools"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(local_tools, "ROOT", root)
    (root / "sample.txt").write_text("same\nsame\n", encoding="utf-8")

    result = local_tools.replace_in_file("sample.txt", "same", "other")

    assert "수정하지 않았습니다" in result
    assert (root / "sample.txt").read_text(encoding="utf-8") == "same\nsame\n"


def test_write_tools_block_unsafe_or_unclear_paths(monkeypatch) -> None:
    root = Path(environ["TEMP"]) / "maos-write-tools"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(local_tools, "ROOT", root)

    assert "경로" in local_tools.write_file("", "x")
    assert "root" in local_tools.write_file("../.env", "x")
    assert "민감 정보" in local_tools.write_file(".env", "x")
    assert "민감 정보" in local_tools.write_file("credentials.txt", "x")
    assert "제외" in local_tools.write_file("node_modules/a.js", "x")
    assert "텍스트 파일" in local_tools.write_file("safe.py", "\0")


def test_review_or_analysis_requests_do_not_select_write_tools() -> None:
    assert registry.coding_tool_for_prompt("이 코드 리뷰해줘") is None
    assert registry.coding_tool_for_prompt("sample.py 분석해줘") == "read_file"
    assert registry.coding_tool_for_prompt("sample.py 설명해줘") == "read_file"


def test_coding_write_registry_requires_explicit_edit_and_payload(monkeypatch) -> None:
    monkeypatch.setattr(registry, "write_file", lambda path, content: pytest.fail("write_file should not run"))
    monkeypatch.setattr(registry, "replace_in_file", lambda path, old_text, new_text: pytest.fail("replace_in_file should not run"))

    assert "수정하지 않았습니다" in registry.execute_registered_tool("write_file", 'backend/app/x.py content="x"')
    assert "수정하지 않았습니다" in registry.execute_registered_tool("write_file", 'backend/app/x.py 수정해줘')
    assert "수정하지 않았습니다" in registry.execute_registered_tool("replace_in_file", 'old_text="a" new_text="b" 수정해줘')


def test_coding_write_tools_are_discovered() -> None:
    response = client.get("/api/tools")
    tool_names = {tool["name"] for tool in response.json()["tools"]}

    assert {"write_file", "replace_in_file"} <= tool_names


def test_run_validation_allows_only_safe_commands(monkeypatch) -> None:
    class Result:
        returncode = 1
        stdout = "ok"
        stderr = "failed"

    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return Result()

    monkeypatch.setattr(local_tools.shutil, "which", lambda command: f"/bin/{command}")
    monkeypatch.setattr(local_tools.subprocess, "run", fake_run)

    result = local_tools.run_validation("pytest")

    assert "exit_code=1" in result
    assert "stdout:\nok" in result
    assert calls[0][0] == ["pytest"]
    assert calls[0][1]["cwd"] == local_tools.ROOT.resolve()
    assert "허용되지 않은" in local_tools.run_validation("git push")
    assert "허용되지 않은" in local_tools.run_validation("npm install")
    assert "허용된 검증 명령" in local_tools.run_validation("python server.py")


def test_run_validation_returns_timeout(monkeypatch) -> None:
    def fake_run(*args, **kwargs):
        raise local_tools.subprocess.TimeoutExpired(cmd=args[0], timeout=1, output="partial", stderr="late")

    monkeypatch.setattr(local_tools.shutil, "which", lambda command: f"/bin/{command}")
    monkeypatch.setattr(local_tools.subprocess, "run", fake_run)

    assert "exit_code=timeout" in local_tools.run_validation("python -m pytest")


def test_run_validation_tool_is_discovered() -> None:
    response = client.get("/api/tools")
    tool_names = {tool["name"] for tool in response.json()["tools"]}

    assert "run_validation" in tool_names


def test_git_diff_is_added_after_write(monkeypatch) -> None:
    monkeypatch.setattr(registry, "write_file", lambda path, content: "changed\nDiff:\n-a\n+b")
    monkeypatch.setattr(registry, "get_git_diff", lambda path: f"diff -- {path}")
    monkeypatch.setattr(registry, "run_validation", lambda command: "exit_code=0\nstdout:\nok\nstderr:")

    result = registry.execute_registered_tool("write_file", 'backend/app/x.py 수정해줘 content="x"')

    assert "Git Diff:\ndiff -- backend/app/x.py" in result
    assert "Validation:" in result


def test_coding_edit_request_uses_replace_tool_when_text_is_explicit(monkeypatch) -> None:
    monkeypatch.setattr(registry, "replace_in_file", lambda path, old_text, new_text: f"replaced {path}: {old_text}->{new_text}\nDiff:\n-ok\n+good")
    monkeypatch.setattr(registry, "run_validation", lambda command: f"exit_code=0\nstdout:\n{command} ok\nstderr:")
    monkeypatch.setattr(registry, "get_git_diff", lambda path: f"git diff for {path}")

    response = client.post(
        "/api/chat",
        json={
            "message": 'sample.py 수정해줘 old_text="ok" new_text="good"',
            "session_id": "coding-replace-flow",
        },
    )
    trace = client.get("/api/observability/traces").json()["traces"][0]

    assert response.status_code == 200
    assert "Diff:" in response.json()["answer"]
    assert "Git Diff:" in response.json()["answer"]
    assert "$ pytest" in response.json()["answer"]
    assert trace["selected_agent"] == "Coding Agent"
    assert trace["selected_tool"] == "replace_in_file"


def test_coding_edit_validation_can_be_skipped(monkeypatch) -> None:
    monkeypatch.setattr(registry, "replace_in_file", lambda path, old_text, new_text: "changed\nDiff:\n-a\n+b")
    monkeypatch.setattr(registry, "get_git_diff", lambda path: "git diff")
    monkeypatch.setattr(registry, "run_validation", lambda command: pytest.fail("validation should not run"))

    response = client.post(
        "/api/chat",
        json={"message": 'backend/app/x.py 수정해줘 old_text="a" new_text="b" 검증하지 마', "session_id": "coding-no-validation"},
    )

    assert response.status_code == 200
    assert "Git Diff:" in response.json()["answer"]
    assert "Validation:" not in response.json()["answer"]


def test_frontend_edit_runs_build_validation(monkeypatch) -> None:
    monkeypatch.setattr(registry, "write_file", lambda path, content: "changed\nDiff:\n-a\n+b")
    monkeypatch.setattr(registry, "get_git_diff", lambda path: f"git diff for {path}")
    monkeypatch.setattr(registry, "run_validation", lambda command: f"exit_code=0\nstdout:\n{command} ok\nstderr:")

    response = client.post(
        "/api/chat",
        json={"message": 'frontend/src/App.tsx 수정해줘 content="export default function App(){return null}"', "session_id": "coding-frontend-validation"},
    )

    assert response.status_code == 200
    assert "$ npm run build" in response.json()["answer"]


def test_coding_edit_self_corrects_once_after_validation_failure(monkeypatch) -> None:
    replace_calls = []
    validation_calls = []

    def fake_replace(path, old_text, new_text):
        replace_calls.append((path, old_text, new_text))
        return f"changed {old_text}->{new_text}\nDiff:\n-{old_text}\n+{new_text}"

    def fake_validation(command):
        validation_calls.append(command)
        if len(validation_calls) == 1:
            return "exit_code=1\nstdout:\nfailed assertion\nstderr:\n"
        return "exit_code=0\nstdout:\npassed\nstderr:"

    async def fake_run_agent(prompt: str, model_name: str | None = None) -> str:
        assert "validation" in prompt.lower()
        return 'replace_in_file path=backend/app/x.py old_text="bad" new_text="good"'

    monkeypatch.setattr(registry, "replace_in_file", fake_replace)
    monkeypatch.setattr(registry, "get_git_diff", lambda path: f"git diff for {path}")
    monkeypatch.setattr(registry, "run_validation", fake_validation)
    monkeypatch.setattr(runner, "run_agent", fake_run_agent)

    response = client.post(
        "/api/chat",
        json={"message": 'backend/app/x.py 수정해줘 old_text="bug" new_text="bad"', "session_id": "coding-self-correct"},
    )

    assert response.status_code == 200
    assert "Self-correction: retry=true" in response.json()["answer"]
    assert "exit_code=0" in response.json()["answer"]
    assert replace_calls == [("backend/app/x.py", "bug", "bad"), ("backend/app/x.py", "bad", "good")]
    assert validation_calls == ["pytest", "pytest"]


def test_coding_edit_self_correction_does_not_retry_without_fix(monkeypatch) -> None:
    monkeypatch.setattr(registry, "replace_in_file", lambda path, old_text, new_text: "changed\nDiff:\n-a\n+b")
    monkeypatch.setattr(registry, "get_git_diff", lambda path: "git diff")
    monkeypatch.setattr(registry, "run_validation", lambda command: "exit_code=1\nstdout:\nfailed\nstderr:")

    async def fake_run_agent(prompt: str, model_name: str | None = None) -> str:
        return "NO_FIX"

    monkeypatch.setattr(runner, "run_agent", fake_run_agent)

    response = client.post(
        "/api/chat",
        json={"message": 'backend/app/x.py 수정해줘 old_text="a" new_text="b"', "session_id": "coding-no-fix"},
    )

    assert response.status_code == 200
    assert "Self-correction: retry=false" in response.json()["answer"]


def test_coding_edit_request_without_patch_reads_file_only(monkeypatch) -> None:
    monkeypatch.setattr(registry, "read_file", lambda path: f"current content from {path}")
    monkeypatch.setattr(registry, "write_file", lambda path, content: pytest.fail("write_file should not run"))

    async def fake_run_agent(prompt: str, model_name: str | None = None) -> str:
        assert "current content from sample.py" in prompt
        return "수정안입니다.\n```python\nprint('ok')\n```"

    monkeypatch.setattr(runner, "run_agent", fake_run_agent)

    response = client.post("/api/chat", json={"message": "sample.py 수정해줘", "session_id": "coding-edit-read-only"})
    trace = client.get("/api/observability/traces").json()["traces"][0]

    assert response.status_code == 200
    assert "수정안입니다" in response.json()["answer"]
    assert trace["selected_agent"] == "Coding Agent"
    assert trace["selected_tool"] == "read_file"


def test_docker_run_request_uses_run_tool(monkeypatch) -> None:
    monkeypatch.setattr(registry, "docker_run", lambda image, name="", detach=True: f"docker run: {image} {name} {detach}")

    response = client.post(
        "/api/chat",
        json={"message": "docker run image=redis:7 name=myredis confirm=true", "session_id": "docker-run-flow"},
    )
    trace = client.get("/api/observability/traces").json()["traces"][0]

    assert response.status_code == 200
    assert response.json()["answer"] == "docker run: redis:7 myredis True"
    assert trace["selected_agent"] == "Docker Agent"
    assert trace["selected_tool"] == "docker_run"


def test_docker_logs_request_uses_logs_tool(monkeypatch) -> None:
    monkeypatch.setattr(registry, "docker_logs", lambda container: f"docker logs: {container}")

    response = client.post("/api/chat", json={"message": "docker logs api", "session_id": "docker-logs-flow"})
    trace = client.get("/api/observability/traces").json()["traces"][0]
    metrics = client.get("/api/observability/metrics").json()

    assert response.status_code == 200
    assert response.json()["answer"] == "docker logs: api"
    assert trace["selected_agent"] == "Docker Agent"
    assert trace["selected_tool"] == "docker_logs"
    assert metrics["last_tool_name"] == "docker_logs"


def test_docker_action_tools_are_discovered() -> None:
    response = client.get("/api/tools")
    tool_names = {tool["name"] for tool in response.json()["tools"]}

    assert {
        "docker_build",
        "docker_run",
        "docker_logs",
        "docker_stop",
        "docker_rm",
        "docker_compose_up",
        "docker_compose_down",
    } <= tool_names


def test_git_request_uses_git_tool(monkeypatch) -> None:
    monkeypatch.setattr(registry, "get_git_status", lambda: "Git 상태 요약입니다.\n- 수정된 파일: 1개\n- 커밋되지 않은 변경사항 있음")

    response = client.post("/api/chat", json={"message": "Git 상태 알려줘", "session_id": "git-flow"})
    trace = client.get("/api/observability/traces").json()["traces"][0]
    metrics = client.get("/api/observability/metrics").json()

    assert response.status_code == 200
    assert "Git 상태 요약" in response.json()["answer"]
    assert trace["selected_agent"] == "Git Agent"
    assert trace["selected_tool"] == "get_git_status"
    assert metrics["last_tool_name"] == "git_status"


def test_git_commit_request_uses_commit_tool(monkeypatch) -> None:
    monkeypatch.setattr(registry, "git_commit", lambda message: f"commit 실행: {message}")

    response = client.post("/api/chat", json={"message": 'git commit -m "test commit" confirm=true', "session_id": "git-commit-flow"})
    trace = client.get("/api/observability/traces").json()["traces"][0]

    assert response.status_code == 200
    assert response.json()["answer"] == "commit 실행: test commit"
    assert trace["selected_agent"] == "Git Agent"
    assert trace["selected_tool"] == "git_commit"


def test_write_tool_requires_confirmation(monkeypatch) -> None:
    monkeypatch.setattr(registry, "git_commit", lambda message: "should not run")

    response = client.post("/api/chat", json={"message": 'git commit -m "test commit"', "session_id": "permission-write"})

    assert response.status_code == 200
    assert "confirm=true" in response.json()["answer"]


def test_destructive_tool_is_blocked(monkeypatch) -> None:
    monkeypatch.setattr(registry, "docker_rm", lambda container: "should not run")

    response = client.post("/api/chat", json={"message": "docker rm container=myredis confirm=true", "session_id": "permission-block"})

    assert response.status_code == 200
    assert "기본 차단" in response.json()["answer"]


def test_git_action_tools_are_discovered() -> None:
    response = client.get("/api/tools")
    tool_names = {tool["name"] for tool in response.json()["tools"]}

    assert {
        "git_add_all",
        "git_commit",
        "git_checkout",
        "git_pull",
        "git_push",
        "git_merge",
        "git_stash",
    } <= tool_names


def test_github_issue_request_uses_issue_tool(monkeypatch) -> None:
    monkeypatch.setattr(registry, "create_github_issue", lambda owner, repo, title, body="": f"issue 생성: {owner}/{repo} {title}")

    response = client.post(
        "/api/chat",
        json={"message": 'GitHub octocat/Hello-World issue title="Bug report" confirm=true', "session_id": "github-issue-flow"},
    )
    trace = client.get("/api/observability/traces").json()["traces"][0]

    assert response.status_code == 200
    assert response.json()["answer"] == "issue 생성: octocat/Hello-World Bug report"
    assert trace["selected_agent"] == "GitHub Agent"
    assert trace["selected_tool"] == "create_github_issue"


def test_github_action_tools_are_discovered() -> None:
    response = client.get("/api/tools")
    tool_names = {tool["name"] for tool in response.json()["tools"]}

    assert {
        "create_github_pull_request",
        "create_github_issue",
        "create_github_release",
        "create_github_branch",
        "github_commit_push",
    } <= tool_names


def test_kubernetes_logs_request_uses_logs_tool(monkeypatch) -> None:
    monkeypatch.setattr(registry, "kubectl_logs", lambda target: f"logs for {target}")

    response = client.post("/api/chat", json={"message": "kubectl logs api-pod", "session_id": "k8s-logs-flow"})
    trace = client.get("/api/observability/traces").json()["traces"][0]

    assert response.status_code == 200
    assert response.json()["answer"] == "logs for api-pod"
    assert trace["selected_agent"] == "Kubernetes Agent"
    assert trace["selected_tool"] == "kubectl_logs"


def test_kubernetes_action_tools_are_discovered() -> None:
    response = client.get("/api/tools")
    tool_names = {tool["name"] for tool in response.json()["tools"]}

    assert {
        "kubectl_apply_file",
        "kubectl_delete",
        "kubectl_scale",
        "kubectl_rollout_restart",
        "kubectl_logs",
        "kubectl_exec",
    } <= tool_names


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
    assert response.json()["memory"][0]["validation_result"].startswith("ok:")
    assert response.json()["memory"][0]["permission_result"] == "none"
    assert response.json()["memory"][0]["final_answer_summary"] == "stored answer"
    assert response.json()["conversations"][0]["role"] == "user"
    assert response.json()["agent_memory"][0]["agent_name"] == "Chat Agent"
    assert "validation_result:" in response.json()["agent_memory"][0]["memory_value"]

    cleared = client.delete("/api/memory/s2")
    assert cleared.status_code == 200
    assert client.get("/api/memory/s2").json()["memory"] == []


def test_memory_redacts_secret_like_values() -> None:
    memory.save_memory(
        "secret-memory",
        user_message="token=abc123 explain this",
        assistant_answer="authorization: Bearer xyz",
        selected_agent="Chat Agent",
        executed_tool_name=None,
        tool_result="api_key=hidden",
    )

    stored = client.get("/api/memory/secret-memory").json()["memory"][0]

    assert "abc123" not in stored["user_message"]
    assert "xyz" not in stored["assistant_answer"]
    assert "hidden" not in stored["tool_result_summary"]


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
