from backend.app.api.schemas import PlannerResult
from backend.app.tools import registry


def plan_message(message: str) -> PlannerResult:
    normalized = message.lower()

    if _mentions_file(normalized):
        return PlannerResult(
            intent="file",
            confidence=0.82,
            reason="파일, 폴더, 프로젝트 구조 확인 요청입니다.",
            suggested_tool=None,
            needs_tool=True,
        )

    if _mentions_code(normalized):
        return PlannerResult(
            intent="code",
            confidence=0.82,
            reason="코드 작성, 수정, 분석 요청입니다.",
            suggested_tool=None,
            needs_tool=False,
        )

    if registry.has_devops_intent(message):
        return PlannerResult(
            intent="k8s" if registry.has_k8s_query_intent(message) else "tool",
            confidence=0.9,
            reason="DevOps 또는 Kubernetes 관련 실행 요청입니다.",
            suggested_tool=_suggested_tool(message),
            needs_tool=True,
        )

    if _explicit_tool_request(normalized) or registry.has_api_intent(message):
        return PlannerResult(
            intent="tool",
            confidence=0.78,
            reason="명확한 도구 실행 또는 외부 정보 조회 요청입니다.",
            suggested_tool=_suggested_tool(message),
            needs_tool=True,
        )

    if _is_chat(normalized):
        return PlannerResult(
            intent="chat",
            confidence=0.8,
            reason="일반 대화 또는 설명 질문입니다.",
            suggested_tool=None,
            needs_tool=False,
        )

    return PlannerResult(
        intent="unknown",
        confidence=0.35,
        reason="명확한 처리 흐름을 분류하지 못했습니다.",
        suggested_tool=None,
        needs_tool=False,
    )


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
    return None


def _mentions_file(normalized: str) -> bool:
    return any(keyword in normalized for keyword in ["파일", "폴더", "디렉터리", "디렉토리", "프로젝트 구조", "file", "folder"])


def _mentions_code(normalized: str) -> bool:
    return any(keyword in normalized for keyword in ["코드", "소스", "함수", "분석", "수정", "작성", "code", "function"])


def _explicit_tool_request(normalized: str) -> bool:
    return any(keyword in normalized for keyword in ["실행", "조회", "확인", "상태", "tool", "run", "check", "status"])


def _is_chat(normalized: str) -> bool:
    return any(keyword in normalized for keyword in ["안녕", "hello", "hi", "뭐야", "무엇", "설명", "explain"])
