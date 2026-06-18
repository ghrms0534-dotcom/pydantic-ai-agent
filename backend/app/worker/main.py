import asyncio

from backend.app.agent import memory, spawn
from backend.app.agent.role_agents import run_role_agent_flow
from backend.app.api.schemas import PlannerResult
from backend.app.queue import get_task_status, pop_task, update_task_status
from backend.app.tools import registry


async def execute_task(task_id: str) -> dict:
    task = get_task_status(task_id)
    if task is None:
        raise ValueError(f"task not found: {task_id}")

    session_id = task["session_id"]
    payload = task["payload"]
    message = payload["message"]
    plan = PlannerResult.model_validate(payload["plan"])
    tool_name = payload.get("tool_name")
    spawned_agent = spawn.spawn_agent(plan.target_agent, plan, session_id)

    update_task_status(task_id, "running")
    memory.save_agent_trace(session_id, "Worker Agent", "worker_task_started", task_id, task["agent_name"])
    try:
        result = await run_role_agent_flow(
            memory.with_memory_context(message, session_id),
            plan,
            tool_name,
            session_id,
            spawned_agent,
        )
    except Exception as exc:
        update_task_status(task_id, "failed", error=str(exc))
        memory.save_agent_trace(session_id, "Worker Agent", "worker_task_failed", task_id, str(exc))
        raise

    update_task_status(task_id, "success", result=result.answer)
    memory.save_memory(
        session_id,
        user_message=message,
        assistant_answer=result.answer,
        selected_agent=result.flow.selection_agent,
        executed_tool_name=tool_name,
        tool_result=result.raw_answer,
        validation_result=(f"{result.validation.reason}: {result.validation.message}" if getattr(result, "validation", None) else "ok"),
        permission_result=registry.permission_result(tool_name, message),
        final_answer_summary=result.answer,
    )
    memory.save_agent_trace(session_id, "Worker Agent", "worker_task_completed", task_id, result.answer)
    return get_task_status(task_id) or {}


async def run_worker() -> None:
    print("maos queue worker started.", flush=True)
    while True:
        task_id = pop_task()
        if task_id is not None:
            await execute_task(task_id)
        await asyncio.sleep(0)


def main() -> None:
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        print("maos queue worker stopped.", flush=True)


if __name__ == "__main__":
    main()
