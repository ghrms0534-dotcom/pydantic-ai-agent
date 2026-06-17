import pytest
from os import environ
from pathlib import Path

from backend.app import queue as task_queue
from backend.app.agent import memory
from backend.app.api.schemas import PlannerResult
from backend.app.worker.main import execute_task


@pytest.fixture(autouse=True)
def clear_memory(monkeypatch, request) -> None:
    test_dir = Path(environ["TEMP"]) / "maos-pytest"
    test_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(char if char.isalnum() else "_" for char in request.node.name)
    monkeypatch.setenv("MAOS_DB_PATH", str(test_dir / f"{safe_name}.db"))
    memory.clear_all_memory()


def test_enqueue_task_records_pending_status(monkeypatch) -> None:
    pushed: list[tuple[str, ...]] = []
    monkeypatch.setattr(task_queue, "_redis_command", lambda *parts: pushed.append(parts) or 1)

    task_id = task_queue.enqueue_task("Git Agent", {"message": "Git 상태 알려줘"}, "queue-session")
    task = task_queue.get_task_status(task_id)

    assert task is not None
    assert task["status"] == "pending"
    assert task["agent_name"] == "Git Agent"
    assert pushed == [("LPUSH", "maos:agent_tasks", task_id)]


@pytest.mark.asyncio
async def test_worker_execute_task_updates_success(monkeypatch) -> None:
    async def fake_run_role_agent_flow(message, plan, tool_name, session_id=None, spawned_agent=None):
        class Result:
            answer = "done"
            raw_answer = "done"
            flow = type("Flow", (), {"selection_agent": "Chat Agent"})()

        return Result()

    monkeypatch.setattr("backend.app.worker.main.run_role_agent_flow", fake_run_role_agent_flow)

    plan = PlannerResult(intent="chat", confidence=0.8, reason="test", needs_tool=False, target_agent="chat")
    task_id = memory.create_task(
        "worker-task",
        "worker-session",
        "Chat Agent",
        {"message": "안녕", "plan": plan.model_dump(), "tool_name": None},
    )["task_id"]

    task = await execute_task(task_id)

    assert task["status"] == "success"
    assert task["result"] == "done"
