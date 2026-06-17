import asyncio
import json
from collections.abc import AsyncIterator
from time import perf_counter
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from backend.app.agent import memory, observability, parallel, spawn, tools
from backend.app.agent.messages import AgentMessage
from backend.app.agent.role_agents import (
    FINAL_ANSWER_AGENT,
    AgentRunResult,
    PLANNER_AGENT,
    TOOL_AGENT,
    PlannerAgent,
    run_role_agent_flow,
    select_agent_flow,
)
from backend.app.api.schemas import AgentStep, AgentStepName, ChatRequest, ChatResponse, PlannerResult
from backend.app.config import get_settings
from backend.app import queue as task_queue
from backend.app.tools import registry


app = FastAPI(title="maos")
CHAT_TIMEOUT_SECONDS = 90

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/tools")
async def get_tools() -> dict[str, list[dict[str, str | bool]]]:
    return {"tools": tools.list_tools()}


@app.get("/api/tools")
async def get_api_tools() -> dict[str, list[dict]]:
    return tools.discovery()


@app.get("/api/agents")
async def get_api_agents() -> dict[str, list[dict]]:
    return {"agents": spawn.list_agent_registry()}


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str) -> dict[str, Any]:
    task = task_queue.get_task_status(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


@app.get("/api/tasks/session/{session_id}")
async def get_session_tasks(session_id: str) -> dict[str, Any]:
    return {"session_id": memory.normalize_session_id(session_id), "tasks": task_queue.list_session_tasks(session_id)}


@app.get("/api/memory/{session_id}")
async def get_memory(session_id: str) -> dict[str, Any]:
    return {
        "session_id": memory.normalize_session_id(session_id),
        "memory": memory.list_memory(session_id),
        "conversations": memory.recent_conversations(session_id),
        "agent_memory": memory.list_agent_memory(session_id),
    }


@app.delete("/api/memory/{session_id}")
async def delete_memory(session_id: str) -> dict[str, str]:
    memory.clear_memory(session_id)
    return {"session_id": memory.normalize_session_id(session_id), "status": "cleared"}


@app.get("/api/trace/{session_id}")
async def get_trace(session_id: str) -> dict[str, Any]:
    return {"session_id": memory.normalize_session_id(session_id), "trace": memory.list_agent_trace(session_id)}


@app.get("/api/observability/metrics")
async def get_observability_metrics() -> dict[str, Any]:
    return observability.get_metrics()


@app.get("/api/observability/traces")
async def get_observability_traces() -> dict[str, list[dict[str, Any]]]:
    return {"traces": observability.list_traces()}


@app.get("/api/observability/traces/{request_id}")
async def get_observability_trace(request_id: str) -> dict[str, Any]:
    trace = observability.get_trace(request_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found.")
    return trace


def _event(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"


def _trace_event(
    step: AgentStepName,
    label: str,
    description: str,
    status: str = "complete",
    *,
    agent: str | None = None,
    tool: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    event = AgentStep(
        step=step,
        label=label,
        description=description,
        status=status,
        agent=agent,
        tool=tool,
        metadata=metadata,
    ).model_dump(exclude_none=True)
    return _event({"type": "trace", **event})


def _router_decision(message: str) -> tuple[str, str]:
    intent = registry.classify_intent(message).value
    if registry.explicitly_requests_multiple_agents(message):
        return intent, "DevOps Agent + API Agent"
    if registry.has_devops_intent(message):
        return intent, "DevOps Agent"
    if registry.has_api_intent(message):
        return intent, "API Agent"
    return intent, "General Orchestrator"


def _selected_tool(message: str) -> str | None:
    normalized = message.lower()
    intent = registry.classify_intent(message)

    if registry.has_git_query_intent(message) and registry.is_registered_tool("get_git_status"):
        return "get_git_status"
    if intent == registry.Intent.SUMMARY and registry.is_registered_tool("summarize_k8s_pods"):
        return "summarize_k8s_pods"
    if intent == registry.Intent.POD and registry.is_registered_tool("get_k8s_pods"):
        return "get_k8s_pods"
    if intent == registry.Intent.DEPLOYMENT and registry.is_registered_tool("get_k8s_deployments"):
        return "get_k8s_deployments"
    if intent == registry.Intent.SERVICE and registry.is_registered_tool("get_k8s_services"):
        return "get_k8s_services"
    if intent == registry.Intent.NAMESPACE and registry.is_registered_tool("get_k8s_namespaces"):
        return "get_k8s_namespaces"
    if intent == registry.Intent.NODE and registry.is_registered_tool("get_k8s_nodes"):
        return "get_k8s_nodes"
    if any(keyword in normalized for keyword in ["public ip", "공인 ip", "퍼블릭 ip"]) and registry.is_registered_tool(
        "get_public_ip"
    ):
        return "get_public_ip"
    if registry.REPO_PATTERN.search(message) and any(
        keyword in normalized for keyword in ["repo", "repository", "저장소", "github"]
    ) and registry.is_registered_tool("get_github_repo_info"):
        return "get_github_repo_info"

    return None


def _planned_tool(plan: PlannerResult, message: str) -> str | None:
    for tool_name in [*plan.required_tools, plan.suggested_tool]:
        if tool_name and registry.is_registered_tool(tool_name):
            return tool_name
    return _selected_tool(message)


def _enqueue_chat_task(session_id: str, message: str, plan: PlannerResult, agent_name: str, tool_name: str | None) -> str:
    return task_queue.enqueue_task(
        agent_name,
        {
            "message": message,
            "plan": plan.model_dump(),
            "tool_name": tool_name,
        },
        session_id,
    )


def _parallel_tool_candidates(message: str, selected_tool: str | None) -> list[str]:
    normalized = message.lower()
    if not any(keyword in normalized for keyword in registry.MULTI_AGENT_KEYWORDS):
        return []

    candidates: list[str] = []
    if registry.has_git_query_intent(message):
        candidates.append("get_git_status")
    if registry.has_k8s_query_intent(message):
        candidates.append(selected_tool if selected_tool and selected_tool.startswith("get_k8s_") else "get_k8s_pods")
    if any(keyword in normalized for keyword in ["public ip", "공인 ip", "퍼블릭 ip"]):
        candidates.append("get_public_ip")
    if registry.REPO_PATTERN.search(message) and any(
        keyword in normalized for keyword in ["github", "repo", "repository", "저장소"]
    ):
        candidates.append("get_github_repo_info")

    unique = [tool for index, tool in enumerate(candidates) if tool not in candidates[:index]]
    return unique if len(unique) > 1 and all(registry.is_registered_tool(tool) for tool in unique) else []


def _activity_intent(intent: str, tool_name: str | None) -> str:
    if tool_name in {
        "get_k8s_pods",
        "summarize_k8s_pods",
        "get_k8s_deployments",
        "get_k8s_services",
        "get_k8s_namespaces",
        "get_k8s_nodes",
    }:
        return "KUBERNETES"
    if tool_name == "get_git_status":
        return "GIT"
    if tool_name == "get_github_repo_info":
        return "GITHUB"
    if tool_name == "get_public_ip":
        return "NETWORK"
    return intent


def _planner_metadata(plan: PlannerResult, router_intent: str, selected_model: str) -> dict[str, Any]:
    return {
        "planner": plan.model_dump(exclude_none=True),
        "intent": router_intent,
        "selected_model": selected_model,
    }


def _send_agent_message(
    request_id: str,
    session_id: str,
    from_agent: str,
    to_agent: str,
    message_type: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> AgentMessage:
    message = AgentMessage(
        request_id=request_id,
        session_id=session_id,
        from_agent=from_agent,
        to_agent=to_agent,
        message_type=message_type,
        content=content,
        metadata=metadata or {},
    )
    observability.record_agent_message(message)
    memory.save_agent_trace(
        session_id,
        from_agent,
        message_type,
        content,
        f"{from_agent} -> {to_agent}",
    )
    observability.add_step(
        request_id,
        "agent_message_sent",
        "success",
        f"{from_agent} -> {to_agent}: {message_type}",
        metadata=message.to_dict(),
    )
    return message


async def _stream_chat_events(request: ChatRequest) -> AsyncIterator[str]:
    message = request.message
    session_id = memory.normalize_session_id(request.session_id)
    request_id = observability.begin_trace(session_id)
    agent_message = memory.with_memory_context(message, session_id)
    loaded_count = len(memory.recent_memory(session_id))
    discovery = tools.discovery()
    plan = await PlannerAgent.plan_async(
        message,
        session_id=session_id,
        available_agents=discovery["agents"],
        available_tools=discovery["tools"],
    )
    spawned_agent = spawn.spawn_agent(plan.target_agent, plan, session_id)
    flow = select_agent_flow(plan, spawned_agent)
    intent, route = _router_decision(message)
    tool_name = _planned_tool(plan, message)
    parallel_tools = _parallel_tool_candidates(message, tool_name)
    activity_intent = _activity_intent(intent, tool_name)
    if get_settings().worker_mode == "queue":
        task_id = _enqueue_chat_task(session_id, message, plan, flow.selection_agent, tool_name)
        yield _trace_event(
            "final_answer",
            "작업 등록",
            "작업이 queue에 등록되었습니다.",
            agent=flow.selection_agent,
            tool=tool_name,
            metadata={"request_id": request_id, "task_id": task_id},
        )
        observability.finish_trace(request_id, "success")
        yield _event({"type": "answer", "answer": f"작업이 등록되었습니다. task_id={task_id}"})
        return

    yield _trace_event(
        "memory_load",
        "Memory 불러오기",
        f"최근 memory {loaded_count}개를 Agent context에 반영했습니다.",
        metadata={"request_id": request_id, "session_id": session_id, "count": loaded_count},
    )
    observability.add_step(
        request_id,
        "memory_load",
        "success",
        f"최근 memory {loaded_count}개를 Agent context에 반영했습니다.",
        metadata={"count": loaded_count},
    )
    yield _trace_event(
        "tool_discovery",
        "Tool Discovery",
        f"사용 가능한 tool {len(discovery['tools'])}개와 agent {len(discovery['agents'])}개를 확인했습니다.",
        metadata={"request_id": request_id, "tools": len(discovery["tools"]), "agents": len(discovery["agents"])},
    )
    observability.add_step(
        request_id,
        "tool_discovery",
        "success",
        f"사용 가능한 tool {len(discovery['tools'])}개와 agent {len(discovery['agents'])}개를 확인했습니다.",
        metadata={"tools": len(discovery["tools"]), "agents": len(discovery["agents"])},
    )
    yield _trace_event(
        "planning",
        "계획 수립",
        f"Planner가 요청을 {plan.intent} 흐름으로 분류했습니다: {activity_intent}",
        agent=PLANNER_AGENT,
        metadata={"request_id": request_id, **_planner_metadata(plan, intent, flow.planning_model)},
    )
    yield _trace_event(
        "planner_agent",
        "Planner Agent",
        f"Planner Agent가 요청을 {plan.intent}로 분류했습니다.",
        agent=PLANNER_AGENT,
        metadata={
            "request_id": request_id,
            "intent": plan.intent,
            "needs_tool": plan.needs_tool,
            "suggested_tool": plan.suggested_tool,
        },
    )
    observability.add_step(
        request_id,
        "planner_agent",
        "success",
        f"요청을 {plan.intent}로 분류했습니다.",
        metadata={"intent": plan.intent, "needs_tool": plan.needs_tool, "suggested_tool": plan.suggested_tool},
    )
    observability.add_step(
        request_id,
        "agent_selected",
        "success",
        f"{flow.selection_agent}를 선택했습니다.",
        metadata={"route": route, "selected_model": flow.selection_model},
    )
    observability.set_selection(
        request_id,
        agent=flow.selection_agent,
        tool=",".join(parallel_tools) if parallel_tools else tool_name,
    )
    next_agent = TOOL_AGENT if tool_name else "Validator Agent"
    _send_agent_message(
        request_id,
        session_id,
        PLANNER_AGENT,
        next_agent,
        "classification",
        f"intent={plan.intent}; needs_tool={plan.needs_tool}; selected_tool={tool_name or 'none'}",
        {"intent": plan.intent, "tool_name": tool_name},
    )
    yield _trace_event(
        "agent_message_sent",
        "Agent Message",
        f"{PLANNER_AGENT} -> {next_agent}",
        agent=PLANNER_AGENT,
        tool=tool_name,
        metadata={"request_id": request_id, "from_agent": PLANNER_AGENT, "to_agent": next_agent},
    )
    yield _trace_event(
        "tool_selection",
        "도구 선택",
        f"{tool_name} 선택됨" if tool_name else "도구 사용 없음",
        agent=flow.selection_agent,
        tool=tool_name,
        metadata={"request_id": request_id, "route": route, "selected_model": flow.selection_model},
    )
    observability.add_step(
        request_id,
        "tool_selected",
        "success" if tool_name else "skipped",
        f"{tool_name} 선택됨" if tool_name else "도구 사용 없음",
        metadata={"tool_name": tool_name},
    )
    yield _trace_event(
        "parallel_execution_decision",
        "Parallel Execution",
        "독립 tool 여러 개를 병렬 실행합니다." if parallel_tools else "병렬 실행 조건이 아니어서 sequential로 진행합니다.",
        status="complete",
        agent=TOOL_AGENT,
        tool=tool_name,
        metadata={"request_id": request_id, "tools": parallel_tools, "mode": "parallel" if parallel_tools else "sequential"},
    )
    observability.add_step(
        request_id,
        "parallel_execution_decision",
        "success" if parallel_tools else "skipped",
        "독립 tool 여러 개를 병렬 실행합니다." if parallel_tools else "병렬 실행 조건이 아니어서 sequential로 진행합니다.",
        metadata={"tools": parallel_tools, "mode": "parallel" if parallel_tools else "sequential"},
    )
    yield _trace_event(
        "tool_execution",
        "도구 실행",
        "Tool Agent가 기존 에이전트 러너 실행 흐름을 호출합니다.",
        status="active",
        agent=TOOL_AGENT,
        tool=tool_name,
        metadata={"request_id": request_id, "selected_model": flow.execution_model},
    )
    observability.add_step(
        request_id,
        "tool_execution_start",
        "success" if tool_name else "skipped",
        "Tool Agent 실행을 시작했습니다." if tool_name else "실행할 tool이 없습니다.",
        metadata={"tool_name": tool_name},
    )
    yield _trace_event(
        "tool_agent",
        "Tool Agent",
        "Tool Agent 실행을 시작했습니다." if tool_name else "일반 대화라 Tool Agent를 건너뜁니다.",
        status="active" if tool_name else "complete",
        agent=TOOL_AGENT,
        tool=tool_name,
        metadata={"request_id": request_id, "skipped": tool_name is None},
    )
    observability.add_step(
        request_id,
        "tool_agent",
        "success" if tool_name else "skipped",
        "Tool Agent 실행을 시작했습니다." if tool_name else "일반 대화라 Tool Agent를 건너뜁니다.",
        metadata={"tool_name": tool_name},
    )

    tool_started = perf_counter()
    try:
        if parallel_tools:
            yield _trace_event(
                "parallel_tool_execution_start",
                "Parallel Tool 실행",
                f"{len(parallel_tools)}개 tool 병렬 실행을 시작합니다.",
                status="active",
                agent=TOOL_AGENT,
                tool=",".join(parallel_tools),
                metadata={"request_id": request_id, "tools": parallel_tools},
            )
            observability.add_step(
                request_id,
                "parallel_tool_execution_start",
                "success",
                f"{len(parallel_tools)}개 tool 병렬 실행을 시작합니다.",
                metadata={"tools": parallel_tools},
            )
            parallel_results = await parallel.run_parallel_tools(message, parallel_tools)
            raw_answer = parallel.format_parallel_results(parallel_results)
            result = AgentRunResult(answer=raw_answer, raw_answer=raw_answer, flow=flow, validation=None)
        else:
            parallel_results = []
            result = await asyncio.wait_for(
                run_role_agent_flow(agent_message, plan, tool_name, session_id, spawned_agent),
                timeout=CHAT_TIMEOUT_SECONDS,
            )
    except TimeoutError:
        duration_ms = (perf_counter() - tool_started) * 1000
        observability.add_step(
            request_id,
            "tool_execution_end",
            "failed",
            "에이전트 응답 시간이 초과되었습니다.",
            duration_ms=duration_ms,
            metadata={"tool_name": tool_name},
        )
        observability.record_tool_execution(
            request_id,
            tool_name=tool_name,
            status="failed",
            duration_ms=duration_ms,
            error_message="timeout",
        )
        observability.finish_trace(request_id, "failed")
        yield _trace_event(
            "tool_execution",
            "실행 실패",
            "에이전트 응답 시간이 초과되었습니다.",
            "error",
            agent=TOOL_AGENT,
            tool=tool_name,
            metadata={"request_id": request_id, "selected_model": flow.execution_model},
        )
        yield _event({"type": "error", "message": "에이전트 응답 시간이 초과되었습니다."})
        return
    except Exception as exc:
        duration_ms = (perf_counter() - tool_started) * 1000
        observability.add_step(
            request_id,
            "tool_execution_end",
            "failed",
            "에이전트 실행 중 오류가 발생했습니다.",
            duration_ms=duration_ms,
            metadata={"tool_name": tool_name},
        )
        observability.record_tool_execution(
            request_id,
            tool_name=tool_name,
            status="failed",
            duration_ms=duration_ms,
            error_message=str(exc),
        )
        observability.finish_trace(request_id, "failed")
        yield _trace_event(
            "tool_execution",
            "실행 실패",
            "에이전트 실행 중 오류가 발생했습니다.",
            "error",
            agent=TOOL_AGENT,
            tool=tool_name,
            metadata={"request_id": request_id, "selected_model": flow.execution_model},
        )
        yield _event({"type": "error", "message": "에이전트 실행 중 오류가 발생했습니다."})
        return

    validation = result.validation
    duration_ms = (perf_counter() - tool_started) * 1000
    parallel_all_failed = bool(parallel_tools) and all(item.status != "success" for item in parallel_results)
    parallel_failed_tools = [item.tool_name for item in parallel_results if item.status != "success"]
    tool_failed = (validation is not None and not validation.ok) or parallel_all_failed
    validation_reason = "parallel_all_failed" if parallel_all_failed else (validation.reason if validation else "ok")
    validation_message = (
        "모든 병렬 tool 실행이 실패했습니다."
        if parallel_all_failed
        else (validation.message if validation else "응답 검증을 완료했습니다.")
    )
    if parallel_tools:
        parallel_payload = [item.to_dict() for item in parallel_results]
        observability.add_step(
            request_id,
            "parallel_tool_execution_end",
            "success" if any(item.status == "success" for item in parallel_results) else "failed",
            "Parallel tool 실행이 완료되었습니다.",
            duration_ms=duration_ms,
            metadata={"tools": parallel_payload},
        )
        observability.record_parallel_tool_executions(request_id, parallel_payload)
        yield _trace_event(
            "parallel_tool_execution_end",
            "Parallel Tool 완료",
            "Parallel tool 실행이 완료되었습니다.",
            agent=TOOL_AGENT,
            tool=",".join(parallel_tools),
            metadata={"request_id": request_id, "tools": parallel_payload},
        )
    observability.add_step(
        request_id,
        "tool_execution_end",
        "failed" if tool_failed else ("success" if tool_name or parallel_tools else "skipped"),
        validation_message if tool_failed else "Tool Agent 실행이 완료되었습니다.",
        duration_ms=duration_ms,
        metadata={"tool_name": tool_name, "parallel_tools": parallel_tools},
    )
    if not parallel_tools:
        observability.record_tool_execution(
            request_id,
            tool_name=tool_name,
            status="failed" if tool_failed else "success",
            duration_ms=duration_ms,
            result=result.raw_answer,
            error_message=validation_message if tool_failed else None,
        )
    if tool_name or parallel_tools:
        _send_agent_message(
            request_id,
            session_id,
            TOOL_AGENT,
            "Validator Agent",
            "tool_result",
            "Tool execution completed.",
            {"tool_name": tool_name, "parallel_tools": parallel_tools, "status": "failed" if tool_failed else "success"},
        )
        yield _trace_event(
            "agent_message_sent",
            "Agent Message",
            f"{TOOL_AGENT} -> Validator Agent",
            agent=TOOL_AGENT,
            tool=tool_name,
            metadata={"request_id": request_id, "from_agent": TOOL_AGENT, "to_agent": "Validator Agent"},
        )
    yield _trace_event(
        "validation",
        "응답 검증",
        validation_message if tool_failed else "Validator Agent가 응답 검증을 완료했습니다.",
        status="error" if tool_failed else "complete",
        agent=result.flow.validation_agent,
        tool=tool_name,
        metadata={
            "request_id": request_id,
            "reason": validation_reason,
            "parallel_failed_tools": parallel_failed_tools,
            "selected_model": result.flow.validation_model,
        },
    )
    observability.add_step(
        request_id,
        "validation",
        "failed" if tool_failed else "success",
        validation_message if tool_failed else "응답 검증을 완료했습니다.",
        metadata={"reason": validation_reason, "parallel_failed_tools": parallel_failed_tools},
    )
    yield _trace_event(
        "validator_agent",
        "Validator Agent",
        validation_message if tool_failed else "Validator Agent가 응답 가능 상태를 확인했습니다.",
        status="error" if tool_failed else "complete",
        agent=result.flow.validation_agent,
        tool=tool_name,
        metadata={"request_id": request_id, "reason": validation_reason, "parallel_failed_tools": parallel_failed_tools},
    )
    observability.add_step(
        request_id,
        "validator_agent",
        "failed" if tool_failed else "success",
        validation_message if tool_failed else "응답 가능 상태를 확인했습니다.",
        metadata={"reason": validation_reason, "parallel_failed_tools": parallel_failed_tools},
    )
    _send_agent_message(
        request_id,
        session_id,
        "Validator Agent",
        FINAL_ANSWER_AGENT,
        "validation_result",
        validation_message,
        {"ok": False if tool_failed else True, "reason": validation_reason},
    )
    yield _trace_event(
        "agent_message_sent",
        "Agent Message",
        f"Validator Agent -> {FINAL_ANSWER_AGENT}",
        agent=result.flow.validation_agent,
        tool=tool_name,
        metadata={"request_id": request_id, "from_agent": "Validator Agent", "to_agent": FINAL_ANSWER_AGENT},
    )
    yield _trace_event(
        "final_answer",
        "최종 응답",
        "Final Answer Agent가 최종 답변을 준비했습니다.",
        agent=FINAL_ANSWER_AGENT,
        tool=tool_name,
        metadata={"request_id": request_id, "selected_model": result.flow.summary_model},
    )
    yield _trace_event(
        "final_answer_agent",
        "Final Answer Agent",
        "Final Answer Agent가 최종 답변을 생성했습니다.",
        agent=FINAL_ANSWER_AGENT,
        tool=tool_name,
        metadata={"request_id": request_id, "selected_model": result.flow.summary_model},
    )
    observability.add_step(request_id, "final_answer_agent", "success", "최종 답변을 생성했습니다.")
    memory.save_memory(
        session_id,
        user_message=message,
        assistant_answer=result.answer,
        selected_agent=result.flow.selection_agent,
        executed_tool_name=",".join(parallel_tools) if parallel_tools else tool_name,
        tool_result=result.raw_answer,
    )
    yield _trace_event(
        "memory_save",
        "Memory 저장",
        "사용자 입력, 최종 답변, 실행 도구 요약을 저장했습니다.",
        agent=result.flow.selection_agent,
        tool=tool_name,
        metadata={"request_id": request_id, "session_id": session_id},
    )
    observability.add_step(request_id, "memory_save", "success", "Memory 저장을 완료했습니다.")
    observability.add_step(request_id, "final_answer", "success", "최종 답변을 생성했습니다.")
    observability.finish_trace(request_id, "success")
    yield _event({"type": "answer", "answer": result.answer})


async def handle_chat(request: ChatRequest) -> ChatResponse:
    session_id = memory.normalize_session_id(request.session_id)
    request_id = observability.begin_trace(session_id)
    agent_message = memory.with_memory_context(request.message, session_id)
    observability.add_step(
        request_id,
        "memory_load",
        "success",
        "최근 memory를 Agent context에 반영했습니다.",
        metadata={"count": len(memory.recent_memory(session_id))},
    )
    discovery = tools.discovery()
    plan = await PlannerAgent.plan_async(
        request.message,
        session_id=session_id,
        available_agents=discovery["agents"],
        available_tools=discovery["tools"],
    )
    spawned_agent = spawn.spawn_agent(plan.target_agent, plan, session_id)
    tool_name = _planned_tool(plan, request.message)
    parallel_tools = _parallel_tool_candidates(request.message, tool_name)
    observability.add_step(
        request_id,
        "tool_discovery",
        "success",
        f"사용 가능한 tool {len(discovery['tools'])}개와 agent {len(discovery['agents'])}개를 확인했습니다.",
        metadata={"tools": len(discovery["tools"]), "agents": len(discovery["agents"])},
    )
    flow = select_agent_flow(plan, spawned_agent)
    observability.set_selection(
        request_id,
        agent=flow.selection_agent,
        tool=",".join(parallel_tools) if parallel_tools else tool_name,
    )
    if get_settings().worker_mode == "queue":
        task_id = _enqueue_chat_task(session_id, request.message, plan, flow.selection_agent, tool_name)
        observability.add_step(request_id, "final_answer", "success", "작업이 queue에 등록되었습니다.")
        observability.finish_trace(request_id, "success")
        return ChatResponse(answer=f"작업이 등록되었습니다. task_id={task_id}")

    observability.add_step(
        request_id,
        "planner_agent",
        "success",
        f"요청을 {plan.intent}로 분류했습니다.",
        metadata={"intent": plan.intent, "needs_tool": plan.needs_tool, "suggested_tool": plan.suggested_tool},
    )
    observability.add_step(request_id, "agent_selected", "success", f"{flow.selection_agent}를 선택했습니다.")
    _send_agent_message(
        request_id,
        session_id,
        PLANNER_AGENT,
        TOOL_AGENT if tool_name else "Validator Agent",
        "classification",
        f"intent={plan.intent}; needs_tool={plan.needs_tool}; selected_tool={tool_name or 'none'}",
        {"intent": plan.intent, "tool_name": tool_name},
    )
    observability.add_step(
        request_id,
        "tool_selected",
        "success" if tool_name else "skipped",
        f"{tool_name} 선택됨" if tool_name else "도구 사용 없음",
    )
    observability.add_step(
        request_id,
        "parallel_execution_decision",
        "success" if parallel_tools else "skipped",
        "독립 tool 여러 개를 병렬 실행합니다." if parallel_tools else "병렬 실행 조건이 아니어서 sequential로 진행합니다.",
        metadata={"tools": parallel_tools, "mode": "parallel" if parallel_tools else "sequential"},
    )
    observability.add_step(
        request_id,
        "tool_execution_start",
        "success" if tool_name else "skipped",
        "Tool Agent 실행을 시작했습니다." if tool_name else "실행할 tool이 없습니다.",
    )
    observability.add_step(
        request_id,
        "tool_agent",
        "success" if tool_name else "skipped",
        "Tool Agent 실행을 시작했습니다." if tool_name else "일반 대화라 Tool Agent를 건너뜁니다.",
        metadata={"tool_name": tool_name},
    )
    tool_started = perf_counter()
    try:
        if parallel_tools:
            observability.add_step(
                request_id,
                "parallel_tool_execution_start",
                "success",
                f"{len(parallel_tools)}개 tool 병렬 실행을 시작합니다.",
                metadata={"tools": parallel_tools},
            )
            parallel_results = await parallel.run_parallel_tools(request.message, parallel_tools)
            raw_answer = parallel.format_parallel_results(parallel_results)
            result = AgentRunResult(answer=raw_answer, raw_answer=raw_answer, flow=flow, validation=None)
        else:
            parallel_results = []
            result = await asyncio.wait_for(
                run_role_agent_flow(agent_message, plan, tool_name, session_id, spawned_agent),
                timeout=CHAT_TIMEOUT_SECONDS,
            )
    except TimeoutError as exc:
        duration_ms = (perf_counter() - tool_started) * 1000
        observability.add_step(
            request_id,
            "tool_execution_end",
            "failed",
            "Agent response timed out.",
            duration_ms=duration_ms,
        )
        observability.record_tool_execution(
            request_id,
            tool_name=tool_name,
            status="failed",
            duration_ms=duration_ms,
            error_message="timeout",
        )
        observability.finish_trace(request_id, "failed")
        raise HTTPException(status_code=504, detail="Agent response timed out.") from exc
    except Exception as exc:
        duration_ms = (perf_counter() - tool_started) * 1000
        observability.add_step(
            request_id,
            "tool_execution_end",
            "failed",
            "Agent execution failed.",
            duration_ms=duration_ms,
        )
        observability.record_tool_execution(
            request_id,
            tool_name=tool_name,
            status="failed",
            duration_ms=duration_ms,
            error_message=str(exc),
        )
        observability.finish_trace(request_id, "failed")
        raise HTTPException(status_code=500, detail="Agent execution failed.") from exc

    duration_ms = (perf_counter() - tool_started) * 1000
    validation = result.validation
    parallel_all_failed = bool(parallel_tools) and all(item.status != "success" for item in parallel_results)
    parallel_failed_tools = [item.tool_name for item in parallel_results if item.status != "success"]
    tool_failed = (validation is not None and not validation.ok) or parallel_all_failed
    validation_reason = "parallel_all_failed" if parallel_all_failed else (validation.reason if validation else "ok")
    validation_message = (
        "모든 병렬 tool 실행이 실패했습니다."
        if parallel_all_failed
        else (validation.message if validation else "응답 검증을 완료했습니다.")
    )
    if parallel_tools:
        parallel_payload = [item.to_dict() for item in parallel_results]
        observability.add_step(
            request_id,
            "parallel_tool_execution_end",
            "success" if any(item.status == "success" for item in parallel_results) else "failed",
            "Parallel tool 실행이 완료되었습니다.",
            duration_ms=duration_ms,
            metadata={"tools": parallel_payload},
        )
        observability.record_parallel_tool_executions(request_id, parallel_payload)
    observability.add_step(
        request_id,
        "tool_execution_end",
        "failed" if tool_failed else ("success" if tool_name or parallel_tools else "skipped"),
        validation_message if tool_failed else "Tool Agent 실행이 완료되었습니다.",
        duration_ms=duration_ms,
    )
    if not parallel_tools:
        observability.record_tool_execution(
            request_id,
            tool_name=tool_name,
            status="failed" if tool_failed else "success",
            duration_ms=duration_ms,
            result=result.raw_answer,
            error_message=validation_message if tool_failed else None,
        )
    if tool_name or parallel_tools:
        _send_agent_message(
            request_id,
            session_id,
            TOOL_AGENT,
            "Validator Agent",
            "tool_result",
            "Tool execution completed.",
            {"tool_name": tool_name, "parallel_tools": parallel_tools, "status": "failed" if tool_failed else "success"},
        )
    observability.add_step(
        request_id,
        "validation",
        "failed" if tool_failed else "success",
        validation_message if tool_failed else "응답 검증을 완료했습니다.",
        metadata={"reason": validation_reason, "parallel_failed_tools": parallel_failed_tools},
    )
    observability.add_step(
        request_id,
        "validator_agent",
        "failed" if tool_failed else "success",
        validation_message if tool_failed else "응답 가능 상태를 확인했습니다.",
        metadata={"reason": validation_reason, "parallel_failed_tools": parallel_failed_tools},
    )
    _send_agent_message(
        request_id,
        session_id,
        "Validator Agent",
        FINAL_ANSWER_AGENT,
        "validation_result",
        validation_message,
        {"ok": False if tool_failed else True, "reason": validation_reason},
    )
    observability.add_step(request_id, "final_answer_agent", "success", "최종 답변을 생성했습니다.")
    memory.save_memory(
        session_id,
        user_message=request.message,
        assistant_answer=result.answer,
        selected_agent=result.flow.selection_agent,
        executed_tool_name=",".join(parallel_tools) if parallel_tools else tool_name,
        tool_result=result.raw_answer,
    )
    observability.add_step(request_id, "memory_save", "success", "Memory 저장을 완료했습니다.")
    observability.add_step(request_id, "final_answer", "success", "최종 답변을 생성했습니다.")
    observability.finish_trace(request_id, "success")
    return ChatResponse(answer=result.answer)


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    return await handle_chat(request)


@app.post("/api/chat", response_model=ChatResponse)
async def api_chat(request: ChatRequest) -> ChatResponse:
    return await handle_chat(request)


@app.post("/api/chat/stream")
async def api_chat_stream(request: ChatRequest) -> StreamingResponse:
    return StreamingResponse(_stream_chat_events(request), media_type="application/x-ndjson")
