import asyncio
import json
from typing import Any

from backend.app.agent import memory
from backend.app.agent.model_router import select_model
from backend.app.agents.local_agent import run_local_agent
from backend.app.api.schemas import PlannerResult
from backend.app.tools import registry


LLM_PLANNER_TIMEOUT_SECONDS = 6


async def plan_message_with_llm(
    user_message: str,
    *,
    session_id: str | None,
    available_agents: list[dict[str, Any]],
    available_tools: list[dict[str, Any]],
) -> PlannerResult:
    _save_trace(session_id, "planning_started", user_message, "")
    try:
        raw = await asyncio.wait_for(
            run_local_agent(_planner_prompt(user_message, available_agents, available_tools), select_model("chat", "Planner Agent", "planning")),
            LLM_PLANNER_TIMEOUT_SECONDS,
        )
        plan = _coerce_plan(json.loads(_json_object(raw)))
        _save_trace(session_id, "planning_completed", user_message, plan.model_dump_json())
        _save_trace(session_id, "selected_agent", user_message, plan.target_agent)
        return plan
    except Exception as exc:
        plan = plan_message(user_message).model_copy(update={"fallback_used": True})
        _save_trace(session_id, "planning_fallback_used", user_message, str(exc))
        _save_trace(session_id, "planning_completed", user_message, plan.model_dump_json())
        _save_trace(session_id, "selected_agent", user_message, plan.target_agent)
        return plan


def plan_message(message: str) -> PlannerResult:
    normalized = message.lower()

    if _mentions_memory(normalized):
        return _plan("memory_status", "system", ["get_memory_status"], True, "Memory status request.", 0.86)

    if _mentions_docker(normalized):
        return _plan("docker_status", "docker", ["get_docker_status"], True, "Docker status request.", 0.86)

    if _mentions_github(normalized, message):
        return _plan("github_repo", "github", ["get_github_repo_info"], True, "GitHub repository request.", 0.84)

    if registry.has_git_query_intent(message):
        return _plan("git_status", "git", ["get_git_status"], True, "Git status request.", 0.9)

    if registry.has_k8s_query_intent(message):
        return _plan("kubernetes_status", "kubernetes", [_suggested_tool(message) or "get_k8s_pods"], True, "Kubernetes status request.", 0.9)

    if _mentions_file(normalized):
        return _plan("file_project_lookup", "file", ["list_project_files"], True, "File or project lookup request.", 0.82)

    if _mentions_system(normalized):
        return _plan("system_status", "system", ["get_public_ip"] if "ip" in normalized else ["get_system_status"], True, "System status request.", 0.78)

    if _mentions_code(normalized):
        return _plan("code", "chat", [], False, "Code analysis request.", 0.82)

    if _explicit_tool_request(normalized) or registry.has_api_intent(message):
        tool = _suggested_tool(message)
        target = "github" if tool == "get_github_repo_info" else "system"
        return _plan("tool", target, [tool] if tool else [], True, "Tool or API lookup request.", 0.78)

    if _is_chat(normalized):
        return _plan("chat", "chat", [], False, "General chat request.", 0.8)

    return _plan("unknown", "unknown", [], False, "Could not classify request.", 0.35)


def _plan(
    intent: str,
    target_agent: str,
    required_tools: list[str],
    needs_tool: bool,
    reason: str,
    confidence: float,
) -> PlannerResult:
    return PlannerResult(
        intent=intent,
        confidence=confidence,
        reason=reason,
        suggested_tool=required_tools[0] if required_tools else None,
        needs_tool=needs_tool,
        target_agent=target_agent,
        required_tools=required_tools,
        steps=_steps(target_agent, needs_tool),
    )


def _coerce_plan(data: dict[str, Any]) -> PlannerResult:
    tools = [tool for tool in data.get("required_tools", []) if isinstance(tool, str) and registry.is_registered_tool(tool)]
    target_agent = str(data.get("target_agent") or "unknown").lower()
    if target_agent not in {"chat", "git", "github", "kubernetes", "docker", "file", "system", "unknown"}:
        target_agent = "unknown"
    if not tools:
        tools = _default_tools_for_agent(target_agent)
    return PlannerResult(
        intent=str(data.get("intent") or "unknown"),
        target_agent=target_agent,
        required_tools=tools,
        steps=[str(step) for step in data.get("steps", [])][:5] or _steps(target_agent, bool(tools)),
        needs_tool=bool(data.get("needs_tool", bool(tools))),
        confidence=float(data.get("confidence", 0.5)),
        reason=str(data.get("reason") or "LLM planner result."),
        suggested_tool=tools[0] if tools else None,
    )


def _planner_prompt(user_message: str, available_agents: list[dict[str, Any]], available_tools: list[dict[str, Any]]) -> str:
    agents = [item.get("name") for item in available_agents]
    tools = [item.get("name") for item in available_tools if item.get("enabled", True)]
    return (
        "Return only one JSON object. No markdown.\n"
        "Classify the user request and produce a small execution plan.\n"
        'target_agent must be one of: "chat", "git", "github", "kubernetes", "docker", "file", "system", "unknown".\n'
        f"available_agents={agents}\n"
        f"available_tools={tools}\n"
        f"user_message={user_message}\n"
        'Schema: {"intent": "...", "target_agent": "...", "required_tools": ["..."], "steps": ["..."], "needs_tool": true, "confidence": 0.8, "reason": "..."}'
    )


def _json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("planner did not return JSON")
    return text[start : end + 1]


def _save_trace(session_id: str | None, step: str, input_text: str, output_text: str) -> None:
    if session_id is not None:
        memory.save_agent_trace(session_id, "Planner Agent", step, input_text, output_text)


def _steps(target_agent: str, needs_tool: bool) -> list[str]:
    if not needs_tool:
        return ["사용자 요청 이해", "한국어로 답변"]
    return [f"{target_agent} 작업 실행", "결과 검증", "한국어로 요약"]


def _suggested_tool(message: str) -> str | None:
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
    if "github" in normalized or registry.REPO_PATTERN.search(message):
        return "get_github_repo_info"
    if "public ip" in normalized or "공인 ip" in normalized or "퍼블릭 ip" in normalized:
        return "get_public_ip"
    if _mentions_memory(normalized):
        return "get_memory_status"
    if _mentions_file(normalized):
        return "list_project_files"
    if _mentions_docker(normalized):
        return "get_docker_status"
    if _mentions_system(normalized):
        return "get_system_status"
    return None


def _mentions_file(normalized: str) -> bool:
    return any(keyword in normalized for keyword in ["파일", "폴더", "디렉터리", "디렉토리", "프로젝트 구조", "file", "folder"])


def _mentions_code(normalized: str) -> bool:
    return any(keyword in normalized for keyword in ["코드", "소스", "함수", "분석", "수정", "작성", "code", "function"])


def _mentions_docker(normalized: str) -> bool:
    return "docker" in normalized or "도커" in normalized


def _mentions_memory(normalized: str) -> bool:
    return "memory" in normalized or "메모리" in normalized


def _mentions_github(normalized: str, message: str) -> bool:
    return "github" in normalized or "repo" in normalized or "repository" in normalized or "저장소" in normalized or registry.REPO_PATTERN.search(message) is not None


def _mentions_system(normalized: str) -> bool:
    return any(keyword in normalized for keyword in ["system", "시스템", "public ip", "공인 ip", "퍼블릭 ip"])


def _default_tools_for_agent(target_agent: str) -> list[str]:
    return {
        "git": ["get_git_status"],
        "github": ["get_github_repo_info"],
        "kubernetes": ["get_k8s_pods"],
        "docker": ["get_docker_status"],
        "file": ["list_project_files"],
        "system": ["get_system_status"],
    }.get(target_agent, [])


def _explicit_tool_request(normalized: str) -> bool:
    return any(keyword in normalized for keyword in ["실행", "조회", "확인", "상태", "tool", "run", "check", "status"])


def _is_chat(normalized: str) -> bool:
    return any(keyword in normalized for keyword in ["안녕", "hello", "hi", "뭐야", "무엇", "설명", "explain"])
