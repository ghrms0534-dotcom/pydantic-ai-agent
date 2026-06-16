import re
from enum import Enum

from pydantic_ai import Agent

from backend.app.tools.apis.github_api import get_github_repo_info
from backend.app.tools.apis.network_api import get_public_ip
from backend.app.tools.devops.git_tools import get_git_status
from backend.app.tools.devops.k8s_tools import (
    get_k8s_deployments,
    get_k8s_namespaces,
    get_k8s_nodes,
    get_k8s_pods,
    get_k8s_services,
    summarize_k8s_pods,
)
from backend.app.tools.validation import run_with_validation_retry


class Intent(str, Enum):
    GENERAL_CHAT = "GENERAL_CHAT"
    GENERAL_KNOWLEDGE = "GENERAL_KNOWLEDGE"
    POD = "POD"
    DEPLOYMENT = "DEPLOYMENT"
    SERVICE = "SERVICE"
    NAMESPACE = "NAMESPACE"
    NODE = "NODE"
    SUMMARY = "SUMMARY"


REPO_PATTERN = re.compile(r"([\w.-]+)[/]([\w.-]+)")
QUERY_KEYWORDS = [
    "현재",
    "상태",
    "조회",
    "확인",
    "보여",
    "보여줘",
    "알려줘",
    "목록",
    "리스트",
    "get",
    "list",
    "status",
    "check",
    "show",
    "describe",
]
EXPLANATION_KEYWORDS = [
    "무엇",
    "뭐야",
    "뭔가",
    "설명",
    "개념",
    "정의",
    "차이",
    "란",
    "어떻게",
    "what is",
    "explain",
    "concept",
]
SUMMARY_KEYWORDS = ["요약", "보기 좋게", "정리", "한눈에", "summary", "summarize"]
K8S_NEGATION_KEYWORDS = ["조회하지 말고", "호출하지 말고", "실행하지 말고", "보여주지 말고"]
MULTI_AGENT_KEYWORDS = ["둘 다", "모두", "같이", "동시에", "비교", "합쳐"]
API_AGENT_KEYWORDS = ["api", "fastapi", "endpoint", "backend", "router", "controller"]
K8S_EXPLANATION = "쿠버네티스는 컨테이너화된 애플리케이션을 배포, 확장, 복구, 관리하기 위한 컨테이너 오케스트레이션 플랫폼입니다."


def register_devops_tools(agent: Agent[None, str]) -> None:
    """Register DevOps-only tools."""

    agent.tool_plain(get_git_status)
    agent.tool_plain(get_k8s_pods)
    agent.tool_plain(get_k8s_deployments)
    agent.tool_plain(get_k8s_services)
    agent.tool_plain(get_k8s_namespaces)
    agent.tool_plain(get_k8s_nodes)
    agent.tool_plain(summarize_k8s_pods)


def register_api_tools(agent: Agent[None, str]) -> None:
    """Register public API-only tools."""

    agent.tool_plain(get_github_repo_info)
    agent.tool_plain(get_public_ip)


def register_tools(agent: Agent[None, str]) -> None:
    """Register all local tools for backward compatibility."""

    register_devops_tools(agent)
    register_api_tools(agent)


def classify_intent(prompt: str) -> Intent:
    normalized = prompt.lower()

    if _is_negated_k8s_query(normalized):
        return Intent.GENERAL_KNOWLEDGE

    wants_explanation = _is_explanation_question(normalized)

    if any(keyword in normalized for keyword in SUMMARY_KEYWORDS) and _mentions_pod(normalized):
        return Intent.SUMMARY

    if _mentions_deployment(normalized) and _has_query_action(normalized):
        return Intent.DEPLOYMENT

    if _mentions_service(normalized) and _has_query_action(normalized):
        return Intent.SERVICE

    if _mentions_node(normalized) and _has_query_action(normalized):
        return Intent.NODE

    if _mentions_pod(normalized) and _has_query_action(normalized):
        return Intent.POD

    if _mentions_namespace(normalized) and _has_query_action(normalized):
        return Intent.NAMESPACE

    if wants_explanation:
        return Intent.GENERAL_KNOWLEDGE

    return Intent.GENERAL_CHAT


def has_k8s_query_intent(prompt: str) -> bool:
    return classify_intent(prompt) in {
        Intent.POD,
        Intent.DEPLOYMENT,
        Intent.SERVICE,
        Intent.NAMESPACE,
        Intent.NODE,
        Intent.SUMMARY,
    }


def has_git_query_intent(prompt: str) -> bool:
    normalized = prompt.lower()
    has_git = "git" in normalized or "깃" in normalized
    has_query_action = any(keyword in normalized for keyword in ["현재", "상태", "조회", "확인", "status", "diff", "log"])
    return has_git and has_query_action


def has_devops_intent(prompt: str) -> bool:
    return has_git_query_intent(prompt) or has_k8s_query_intent(prompt)


def has_api_intent(prompt: str) -> bool:
    normalized = prompt.lower()
    has_repo = REPO_PATTERN.search(prompt) is not None
    has_api_keyword = any(keyword in normalized for keyword in API_AGENT_KEYWORDS)
    has_public_api_tool = any(
        keyword in normalized
        for keyword in [
            "public ip",
            "공인 ip",
            "퍼블릭 ip",
            "github",
            "repo",
            "repository",
            "저장소",
        ]
    )
    return has_api_keyword or has_public_api_tool or has_repo


def explicitly_requests_multiple_agents(prompt: str) -> bool:
    normalized = prompt.lower()
    mentions_devops = has_devops_intent(prompt) or "devops" in normalized
    mentions_api = has_api_intent(prompt) or "api agent" in normalized
    asks_multi = any(keyword in normalized for keyword in MULTI_AGENT_KEYWORDS)
    return mentions_devops and mentions_api and asks_multi


def route_devops_tool_call(prompt: str) -> str | None:
    """Route clear DevOps prompts directly to DevOps tools."""

    if has_git_query_intent(prompt):
        return get_git_status()

    intent = classify_intent(prompt)
    namespace = _extract_namespace(prompt.lower())
    prefix = _k8s_explanation_prefix(prompt)

    if intent == Intent.SUMMARY:
        result, _validation = run_with_validation_retry("summarize_k8s_pods", summarize_k8s_pods)
        return prefix + result
    if intent == Intent.POD:
        result, _validation = run_with_validation_retry("get_k8s_pods", lambda: get_k8s_pods(namespace=namespace))
        return prefix + result
    if intent == Intent.DEPLOYMENT:
        result, _validation = run_with_validation_retry("get_k8s_deployments", get_k8s_deployments)
        return prefix + result
    if intent == Intent.SERVICE:
        result, _validation = run_with_validation_retry("get_k8s_services", get_k8s_services)
        return prefix + result
    if intent == Intent.NAMESPACE:
        result, _validation = run_with_validation_retry("get_k8s_namespaces", get_k8s_namespaces)
        return prefix + result
    if intent == Intent.NODE:
        result, _validation = run_with_validation_retry("get_k8s_nodes", get_k8s_nodes)
        return prefix + result

    return None


def route_api_tool_call(prompt: str) -> str | None:
    """Route clear public API prompts directly to API tools."""

    normalized = prompt.lower()

    repo_match = REPO_PATTERN.search(prompt)
    if repo_match and any(keyword in normalized for keyword in ["repo", "repository", "저장소", "github"]):
        owner, repo = repo_match.groups()
        return get_github_repo_info(owner=owner, repo=repo)

    if any(keyword in normalized for keyword in ["public ip", "공인 ip", "퍼블릭 ip"]):
        return get_public_ip()

    return None


def route_tool_call(prompt: str) -> str | None:
    """Route clear prompts to any local tool for backward compatibility."""

    return route_devops_tool_call(prompt) or route_api_tool_call(prompt)


def _has_query_action(normalized: str) -> bool:
    return any(keyword in normalized for keyword in QUERY_KEYWORDS)


def _is_explanation_question(normalized: str) -> bool:
    return any(keyword in normalized for keyword in EXPLANATION_KEYWORDS)


def _is_negated_k8s_query(normalized: str) -> bool:
    return any(keyword in normalized for keyword in K8S_NEGATION_KEYWORDS)


def _mentions_pod(normalized: str) -> bool:
    return any(keyword in normalized for keyword in ["pod", "pods", "파드"])


def _mentions_deployment(normalized: str) -> bool:
    return any(keyword in normalized for keyword in ["deployment", "deployments", "디플로이먼트"])


def _mentions_service(normalized: str) -> bool:
    return any(keyword in normalized for keyword in ["service", "services", "서비스"])


def _mentions_namespace(normalized: str) -> bool:
    return any(keyword in normalized for keyword in ["namespace", "namespaces", "네임스페이스"])


def _mentions_node(normalized: str) -> bool:
    return any(keyword in normalized for keyword in ["node", "nodes", "노드"])


def _extract_namespace(normalized: str) -> str | None:
    namespace_patterns = [
        r"(?:namespace|네임스페이스)\s+([a-z0-9][a-z0-9.-]*)",
        r"([a-z0-9][a-z0-9.-]*)\s+(?:namespace|네임스페이스)",
    ]
    for pattern in namespace_patterns:
        match = re.search(pattern, normalized)
        if match:
            namespace = match.group(1)
            if namespace not in {"pod", "pods", "파드"}:
                return namespace

    if "kube-system" in normalized:
        return "kube-system"
    return None


def _k8s_explanation_prefix(prompt: str) -> str:
    normalized = prompt.lower()
    if _is_explanation_question(normalized) and not _is_negated_k8s_query(normalized):
        return f"{K8S_EXPLANATION}\n\n"
    return ""
