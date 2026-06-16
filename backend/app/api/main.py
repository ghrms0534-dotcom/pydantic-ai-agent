import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from backend.app.agent import tools
from backend.app.agent.planner import plan_message
from backend.app.agent.role_agents import PLANNER_AGENT, TOOL_AGENT, run_role_agent_flow, select_agent_flow
from backend.app.api.schemas import AgentStep, AgentStepName, ChatRequest, ChatResponse, PlannerResult
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
async def get_tools() -> dict[str, list[dict[str, str]]]:
    return {"tools": tools.list_tools()}


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

    if registry.has_git_query_intent(message):
        return "get_git_status"
    if intent == registry.Intent.SUMMARY:
        return "summarize_k8s_pods"
    if intent == registry.Intent.POD:
        return "get_k8s_pods"
    if intent == registry.Intent.DEPLOYMENT:
        return "get_k8s_deployments"
    if intent == registry.Intent.SERVICE:
        return "get_k8s_services"
    if intent == registry.Intent.NAMESPACE:
        return "get_k8s_namespaces"
    if intent == registry.Intent.NODE:
        return "get_k8s_nodes"
    if any(keyword in normalized for keyword in ["public ip", "공인 ip", "퍼블릭 ip"]):
        return "get_public_ip"
    if registry.REPO_PATTERN.search(message) and any(
        keyword in normalized for keyword in ["repo", "repository", "저장소", "github"]
    ):
        return "get_github_repo_info"

    return None


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


async def _stream_chat_events(message: str) -> AsyncIterator[str]:
    plan = plan_message(message)
    flow = select_agent_flow(plan)
    intent, route = _router_decision(message)
    tool_name = _selected_tool(message)
    activity_intent = _activity_intent(intent, tool_name)

    yield _trace_event(
        "planning",
        "계획 수립",
        f"Planner가 요청을 {plan.intent} 흐름으로 분류했습니다: {activity_intent}",
        agent=PLANNER_AGENT,
        metadata=_planner_metadata(plan, intent, flow.planning_model),
    )
    yield _trace_event(
        "tool_selection",
        "도구 선택",
        f"{tool_name} 선택됨" if tool_name else "도구 사용 없음",
        agent=flow.selection_agent,
        tool=tool_name,
        metadata={"route": route, "selected_model": flow.selection_model},
    )
    yield _trace_event(
        "tool_execution",
        "도구 실행",
        "Tool Agent가 기존 에이전트 러너 실행 흐름을 호출합니다.",
        status="active",
        agent=TOOL_AGENT,
        tool=tool_name,
        metadata={"selected_model": flow.execution_model},
    )

    try:
        result = await asyncio.wait_for(
            run_role_agent_flow(message, plan, tool_name),
            timeout=CHAT_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        yield _trace_event(
            "tool_execution",
            "실행 실패",
            "에이전트 응답 시간이 초과되었습니다.",
            "error",
            agent=TOOL_AGENT,
            tool=tool_name,
            metadata={"selected_model": flow.execution_model},
        )
        yield _event({"type": "error", "message": "에이전트 응답 시간이 초과되었습니다."})
        return
    except Exception:
        yield _trace_event(
            "tool_execution",
            "실행 실패",
            "에이전트 실행 중 오류가 발생했습니다.",
            "error",
            agent=TOOL_AGENT,
            tool=tool_name,
            metadata={"selected_model": flow.execution_model},
        )
        yield _event({"type": "error", "message": "에이전트 실행 중 오류가 발생했습니다."})
        return

    validation = result.validation
    yield _trace_event(
        "validation",
        "응답 검증",
        validation.message if validation and not validation.ok else "Validator Agent가 응답 검증을 완료했습니다.",
        status="error" if validation and not validation.ok else "complete",
        agent=result.flow.validation_agent,
        tool=tool_name,
        metadata={
            "reason": validation.reason if validation else "no_tool",
            "selected_model": result.flow.validation_model,
        },
    )
    yield _trace_event(
        "final_answer",
        "최종 응답",
        "Summary Agent가 최종 답변을 준비했습니다.",
        agent=result.flow.summary_agent,
        tool=tool_name,
        metadata={"selected_model": result.flow.summary_model},
    )
    yield _event({"type": "answer", "answer": result.answer})


async def handle_chat(request: ChatRequest) -> ChatResponse:
    plan = plan_message(request.message)
    tool_name = _selected_tool(request.message)
    try:
        result = await asyncio.wait_for(
            run_role_agent_flow(request.message, plan, tool_name),
            timeout=CHAT_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Agent response timed out.") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Agent execution failed.") from exc

    return ChatResponse(answer=result.answer)


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    return await handle_chat(request)


@app.post("/api/chat", response_model=ChatResponse)
async def api_chat(request: ChatRequest) -> ChatResponse:
    return await handle_chat(request)


@app.post("/api/chat/stream")
async def api_chat_stream(request: ChatRequest) -> StreamingResponse:
    return StreamingResponse(_stream_chat_events(request.message), media_type="application/x-ndjson")
