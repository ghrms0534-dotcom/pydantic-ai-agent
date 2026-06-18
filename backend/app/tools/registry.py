import re
from dataclasses import dataclass
from enum import Enum

from pydantic_ai import Agent

from backend.app.tools.apis.github_api import (
    create_github_branch,
    create_github_issue,
    create_github_pull_request,
    create_github_release,
    get_github_repo_info,
    github_commit_push,
)
from backend.app.tools.apis.network_api import get_public_ip
from backend.app.tools.devops.git_tools import (
    get_git_branch,
    get_git_diff,
    get_git_status,
    git_add_all,
    git_checkout,
    git_commit,
    git_merge,
    git_pull,
    git_push,
    git_stash,
)
from backend.app.tools.devops.k8s_tools import (
    get_k8s_deployments,
    get_k8s_namespaces,
    get_k8s_nodes,
    get_k8s_pods,
    get_k8s_services,
    kubectl_apply_file,
    kubectl_delete,
    kubectl_exec,
    kubectl_logs,
    kubectl_rollout_restart,
    kubectl_scale,
    summarize_k8s_pods,
)
from backend.app.tools.local_tools import (
    docker_build,
    docker_compose_down,
    docker_compose_up,
    docker_logs,
    docker_rm,
    docker_run,
    docker_stop,
    get_docker_status,
    get_memory_status,
    get_system_status,
    list_directory,
    list_project_files,
    read_file,
    replace_in_file,
    run_validation,
    search_code,
    write_file,
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
WRITE_TOOLS = {
    "git_add_all",
    "git_commit",
    "git_push",
    "create_github_pull_request",
    "create_github_issue",
    "create_github_release",
    "create_github_branch",
    "github_commit_push",
    "kubectl_apply_file",
    "kubectl_scale",
    "kubectl_rollout_restart",
    "docker_build",
    "docker_run",
    "docker_compose_up",
}
DESTRUCTIVE_TOOLS = {
    "git_checkout",
    "git_merge",
    "git_stash",
    "kubectl_delete",
    "kubectl_exec",
    "docker_stop",
    "docker_rm",
    "docker_compose_down",
}


@dataclass(frozen=True)
class RegistryItem:
    name: str
    display_name: str
    description: str
    category: str
    source: str


REGISTERED_TOOLS = [
    RegistryItem("get_git_status", "Git Agent", "Run git status --short.", "devops", "builtin"),
    RegistryItem("get_git_branch", "Git Agent", "Show current git branch.", "devops", "builtin"),
    RegistryItem("git_add_all", "Git Agent", "Run git add .", "devops", "builtin"),
    RegistryItem("git_commit", "Git Agent", "Run git commit -m.", "devops", "builtin"),
    RegistryItem("git_checkout", "Git Agent", "Run git checkout.", "devops", "builtin"),
    RegistryItem("git_pull", "Git Agent", "Run git pull.", "devops", "builtin"),
    RegistryItem("git_push", "Git Agent", "Run git push.", "devops", "builtin"),
    RegistryItem("git_merge", "Git Agent", "Run git merge.", "devops", "builtin"),
    RegistryItem("git_stash", "Git Agent", "Run git stash.", "devops", "builtin"),
    RegistryItem("get_k8s_pods", "Kubernetes Agent", "Run kubectl get pods -A.", "devops", "builtin"),
    RegistryItem("get_k8s_deployments", "Kubernetes Deployments", "Run kubectl get deployments -A.", "devops", "builtin"),
    RegistryItem("get_k8s_services", "Kubernetes Services", "Run kubectl get services -A.", "devops", "builtin"),
    RegistryItem("get_k8s_namespaces", "Kubernetes Namespaces", "Run kubectl get namespaces.", "devops", "builtin"),
    RegistryItem("get_k8s_nodes", "Kubernetes Nodes", "Run kubectl get nodes.", "devops", "builtin"),
    RegistryItem("summarize_k8s_pods", "Kubernetes Pod Summary", "Summarize Kubernetes pod status.", "devops", "builtin"),
    RegistryItem("kubectl_apply_file", "Kubernetes Agent", "Run kubectl apply -f.", "devops", "builtin"),
    RegistryItem("kubectl_delete", "Kubernetes Agent", "Run kubectl delete.", "devops", "builtin"),
    RegistryItem("kubectl_scale", "Kubernetes Agent", "Run kubectl scale.", "devops", "builtin"),
    RegistryItem("kubectl_rollout_restart", "Kubernetes Agent", "Run kubectl rollout restart.", "devops", "builtin"),
    RegistryItem("kubectl_logs", "Kubernetes Agent", "Run kubectl logs.", "devops", "builtin"),
    RegistryItem("kubectl_exec", "Kubernetes Agent", "Run kubectl exec.", "devops", "builtin"),
    RegistryItem("get_github_repo_info", "GitHub Agent", "Fetch public GitHub repository information.", "api", "builtin"),
    RegistryItem("create_github_pull_request", "GitHub Agent", "Create GitHub pull request.", "api", "builtin"),
    RegistryItem("create_github_issue", "GitHub Agent", "Create GitHub issue.", "api", "builtin"),
    RegistryItem("create_github_release", "GitHub Agent", "Create GitHub release.", "api", "builtin"),
    RegistryItem("create_github_branch", "GitHub Agent", "Create GitHub branch.", "api", "builtin"),
    RegistryItem("github_commit_push", "GitHub Agent", "Commit and push file through GitHub contents API.", "api", "builtin"),
    RegistryItem("get_public_ip", "Network Tool", "Fetch the current public IP address.", "api", "builtin"),
    RegistryItem("list_project_files", "File Agent", "List project files.", "file", "builtin"),
    RegistryItem("list_directory", "Coding Agent", "List a project directory read-only.", "coding", "builtin"),
    RegistryItem("read_file", "Coding Agent", "Read a project text file read-only.", "coding", "builtin"),
    RegistryItem("search_code", "Coding Agent", "Search project text files read-only.", "coding", "builtin"),
    RegistryItem("write_file", "Coding Agent", "Write a project text file safely.", "coding", "builtin"),
    RegistryItem("replace_in_file", "Coding Agent", "Replace exact text in a project file safely.", "coding", "builtin"),
    RegistryItem("run_validation", "Coding Agent", "Run an allowed validation command safely.", "coding", "builtin"),
    RegistryItem("get_memory_status", "System Agent", "Show SQLite memory status.", "system", "builtin"),
    RegistryItem("get_docker_status", "Docker Agent", "Show Docker container status.", "devops", "builtin"),
    RegistryItem("docker_build", "Docker Agent", "Run docker build.", "devops", "builtin"),
    RegistryItem("docker_run", "Docker Agent", "Run docker run.", "devops", "builtin"),
    RegistryItem("docker_logs", "Docker Agent", "Run docker logs.", "devops", "builtin"),
    RegistryItem("docker_stop", "Docker Agent", "Run docker stop.", "devops", "builtin"),
    RegistryItem("docker_rm", "Docker Agent", "Run docker rm.", "devops", "builtin"),
    RegistryItem("docker_compose_up", "Docker Agent", "Run docker compose up.", "devops", "builtin"),
    RegistryItem("docker_compose_down", "Docker Agent", "Run docker compose down.", "devops", "builtin"),
    RegistryItem("get_system_status", "System Agent", "Show basic system status.", "system", "builtin"),
]

REGISTERED_AGENTS = [
    RegistryItem("coding", "Coding Agent", "Code explanation, review, small fixes, and snippets", "agent", "agent"),
    RegistryItem("git", "Git Agent", "Git 저장소 상태 확인", "agent", "agent"),
    RegistryItem("github", "GitHub Agent", "GitHub 저장소 정보 조회", "agent", "agent"),
    RegistryItem("kubernetes", "Kubernetes Agent", "Kubernetes 리소스 조회", "agent", "agent"),
    RegistryItem("docker", "Docker Agent", "Docker 환경 관리", "agent", "agent"),
]


def registered_tools() -> list[RegistryItem]:
    return REGISTERED_TOOLS.copy()


def registered_agents() -> list[RegistryItem]:
    return REGISTERED_AGENTS.copy()


def is_registered_tool(tool_name: str) -> bool:
    return any(tool.name == tool_name for tool in REGISTERED_TOOLS)


def register_devops_tools(agent: Agent[None, str]) -> None:
    """Register DevOps-only tools."""

    agent.tool_plain(get_git_status)
    agent.tool_plain(get_git_branch)
    agent.tool_plain(git_add_all)
    agent.tool_plain(git_commit)
    agent.tool_plain(git_checkout)
    agent.tool_plain(git_pull)
    agent.tool_plain(git_push)
    agent.tool_plain(git_merge)
    agent.tool_plain(git_stash)
    agent.tool_plain(get_k8s_pods)
    agent.tool_plain(get_k8s_deployments)
    agent.tool_plain(get_k8s_services)
    agent.tool_plain(get_k8s_namespaces)
    agent.tool_plain(get_k8s_nodes)
    agent.tool_plain(summarize_k8s_pods)
    agent.tool_plain(kubectl_apply_file)
    agent.tool_plain(kubectl_delete)
    agent.tool_plain(kubectl_scale)
    agent.tool_plain(kubectl_rollout_restart)
    agent.tool_plain(kubectl_logs)
    agent.tool_plain(kubectl_exec)
    agent.tool_plain(get_docker_status)
    agent.tool_plain(docker_build)
    agent.tool_plain(docker_run)
    agent.tool_plain(docker_logs)
    agent.tool_plain(docker_stop)
    agent.tool_plain(docker_rm)
    agent.tool_plain(docker_compose_up)
    agent.tool_plain(docker_compose_down)


def register_api_tools(agent: Agent[None, str]) -> None:
    """Register public API-only tools."""

    agent.tool_plain(get_github_repo_info)
    agent.tool_plain(create_github_pull_request)
    agent.tool_plain(create_github_issue)
    agent.tool_plain(create_github_release)
    agent.tool_plain(create_github_branch)
    agent.tool_plain(github_commit_push)
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
    return k8s_tool_for_prompt(prompt) is not None or classify_intent(prompt) in {
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
    has_query_action = any(
        keyword in normalized
        for keyword in [
            "현재",
            "상태",
            "조회",
            "확인",
            "status",
            "diff",
            "log",
            "branch",
            "add",
            "commit",
            "checkout",
            "pull",
            "push",
            "merge",
            "stash",
        ]
    )
    return has_git and has_query_action


def has_devops_intent(prompt: str) -> bool:
    return has_git_query_intent(prompt) or has_k8s_query_intent(prompt) or docker_tool_for_prompt(prompt) is not None


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

    git_tool = git_tool_for_prompt(prompt)
    if git_tool:
        return execute_registered_tool(git_tool, prompt)
    k8s_tool = k8s_tool_for_prompt(prompt)
    if k8s_tool:
        return execute_registered_tool(k8s_tool, prompt)
    docker_tool = docker_tool_for_prompt(prompt)
    if docker_tool:
        return execute_registered_tool(docker_tool, prompt)

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

    github_tool = github_tool_for_prompt(prompt)
    if github_tool:
        return execute_registered_tool(github_tool, prompt)

    if any(keyword in normalized for keyword in ["public ip", "공인 ip", "퍼블릭 ip"]):
        return get_public_ip()

    return None


def route_tool_call(prompt: str) -> str | None:
    """Route clear prompts to any local tool for backward compatibility."""

    return route_devops_tool_call(prompt) or route_api_tool_call(prompt)


def execute_registered_tool(tool_name: str, prompt: str, session_id: str | None = None) -> str:
    permission_error = _permission_error(tool_name, prompt)
    if permission_error:
        return permission_error

    if tool_name == "get_git_status":
        return get_git_status()
    if tool_name == "get_git_branch":
        return get_git_branch()
    if tool_name == "git_add_all":
        return git_add_all()
    if tool_name == "git_commit":
        return git_commit(_extract_commit_message(prompt))
    if tool_name == "git_checkout":
        return git_checkout(_extract_git_target(prompt, "checkout"))
    if tool_name == "git_pull":
        return git_pull()
    if tool_name == "git_push":
        return git_push()
    if tool_name == "git_merge":
        return git_merge(_extract_git_target(prompt, "merge"))
    if tool_name == "git_stash":
        return git_stash()
    if tool_name == "get_k8s_pods":
        return get_k8s_pods(namespace=_extract_namespace(prompt.lower()))
    if tool_name == "get_k8s_deployments":
        return get_k8s_deployments()
    if tool_name == "get_k8s_services":
        return get_k8s_services()
    if tool_name == "get_k8s_namespaces":
        return get_k8s_namespaces()
    if tool_name == "get_k8s_nodes":
        return get_k8s_nodes()
    if tool_name == "summarize_k8s_pods":
        return summarize_k8s_pods()
    if tool_name == "kubectl_apply_file":
        return kubectl_apply_file(_extract_value(prompt, "file") or _extract_after(prompt, "-f"))
    if tool_name == "kubectl_delete":
        return kubectl_delete(_extract_kubectl_target(prompt, "delete"))
    if tool_name == "kubectl_scale":
        return kubectl_scale(_extract_kubectl_target(prompt, "scale"), _extract_value(prompt, "replicas") or _extract_value(prompt, "replica"))
    if tool_name == "kubectl_rollout_restart":
        return kubectl_rollout_restart(_extract_kubectl_target(prompt, "restart"))
    if tool_name == "kubectl_logs":
        return kubectl_logs(_extract_kubectl_target(prompt, "logs"))
    if tool_name == "kubectl_exec":
        return kubectl_exec(_extract_kubectl_target(prompt, "exec"), _extract_value(prompt, "command") or _extract_after(prompt, "--"))
    if tool_name == "get_github_repo_info":
        owner, repo = _extract_repo(prompt)
        return get_github_repo_info(owner=owner, repo=repo)
    if tool_name == "create_github_pull_request":
        owner, repo = _extract_repo(prompt)
        return create_github_pull_request(owner, repo, _extract_value(prompt, "title"), _extract_value(prompt, "head"), _extract_value(prompt, "base") or "main", _extract_value(prompt, "body"))
    if tool_name == "create_github_issue":
        owner, repo = _extract_repo(prompt)
        return create_github_issue(owner, repo, _extract_value(prompt, "title"), _extract_value(prompt, "body"))
    if tool_name == "create_github_release":
        owner, repo = _extract_repo(prompt)
        return create_github_release(owner, repo, _extract_value(prompt, "tag"), _extract_value(prompt, "name"), _extract_value(prompt, "body"))
    if tool_name == "create_github_branch":
        owner, repo = _extract_repo(prompt)
        return create_github_branch(owner, repo, _extract_value(prompt, "branch") or _extract_value(prompt, "name"), _extract_value(prompt, "from") or "main")
    if tool_name == "github_commit_push":
        owner, repo = _extract_repo(prompt)
        return github_commit_push(owner, repo, _extract_value(prompt, "path"), _extract_value(prompt, "content"), _extract_value(prompt, "message"), _extract_value(prompt, "branch") or "main")
    if tool_name == "get_public_ip":
        return get_public_ip()
    if tool_name == "list_project_files":
        return list_project_files()
    if tool_name == "list_directory":
        return list_directory(_extract_directory_path(prompt))
    if tool_name == "read_file":
        return read_file(_extract_file_path(prompt))
    if tool_name == "search_code":
        return search_code(_extract_search_keyword(prompt))
    if tool_name == "write_file":
        path = _extract_file_path(prompt)
        if not _can_execute_coding_write(prompt, path):
            return "명시적 수정 요청과 파일 경로가 없어 파일을 수정하지 않았습니다."
        return _with_post_write_validation(write_file(path, _extract_value(prompt, "content")), path, prompt)
    if tool_name == "replace_in_file":
        path = _extract_file_path(prompt)
        if not _can_execute_coding_write(prompt, path):
            return "명시적 수정 요청과 파일 경로가 없어 파일을 수정하지 않았습니다."
        return _with_post_write_validation(replace_in_file(path, _extract_value(prompt, "old_text"), _extract_value(prompt, "new_text")), path, prompt)
    if tool_name == "run_validation":
        return run_validation(_extract_value(prompt, "command") or _extract_after(prompt, "run_validation"))
    if tool_name == "get_memory_status":
        return get_memory_status(session_id)
    if tool_name == "get_docker_status":
        return get_docker_status()
    if tool_name == "docker_build":
        return docker_build(_extract_value(prompt, "path") or _extract_docker_build_path(prompt), _extract_value(prompt, "tag") or _extract_after(prompt, "-t"))
    if tool_name == "docker_run":
        return docker_run(_extract_value(prompt, "image") or _extract_docker_image(prompt), _extract_value(prompt, "name"), "--no-detach" not in prompt.lower())
    if tool_name == "docker_logs":
        return docker_logs(_extract_value(prompt, "container") or _extract_after(prompt, "logs"))
    if tool_name == "docker_stop":
        return docker_stop(_extract_value(prompt, "container") or _extract_after(prompt, "stop"))
    if tool_name == "docker_rm":
        return docker_rm(_extract_value(prompt, "container") or _extract_after(prompt, "rm") or _extract_after(prompt, "remove"))
    if tool_name == "docker_compose_up":
        return docker_compose_up("--no-detach" not in prompt.lower())
    if tool_name == "docker_compose_down":
        return docker_compose_down()
    if tool_name == "get_system_status":
        return get_system_status()
    return f"등록되지 않은 tool입니다: {tool_name}"


def _has_query_action(normalized: str) -> bool:
    return any(keyword in normalized for keyword in QUERY_KEYWORDS)


def git_tool_for_prompt(prompt: str) -> str | None:
    normalized = prompt.lower()
    if "commit" in normalized:
        return "git_commit"
    if "checkout" in normalized:
        return "git_checkout"
    if "pull" in normalized:
        return "git_pull"
    if "push" in normalized:
        return "git_push"
    if "merge" in normalized:
        return "git_merge"
    if "stash" in normalized:
        return "git_stash"
    if "add" in normalized:
        return "git_add_all"
    if "branch" in normalized or "브랜치" in normalized:
        return "get_git_branch"
    if has_git_query_intent(prompt):
        return "get_git_status"
    return None


def github_tool_for_prompt(prompt: str) -> str | None:
    normalized = prompt.lower()
    if "github" not in normalized and REPO_PATTERN.search(prompt) is None:
        return None
    if "pull request" in normalized or " pr " in f" {normalized} ":
        return "create_github_pull_request"
    if "issue" in normalized or "이슈" in normalized:
        return "create_github_issue"
    if "release" in normalized or "릴리즈" in normalized:
        return "create_github_release"
    if "branch" in normalized or "브랜치" in normalized:
        return "create_github_branch"
    if "commit" in normalized and "push" in normalized:
        return "github_commit_push"
    if any(keyword in normalized for keyword in ["repo", "repository", "저장소", "github"]):
        return "get_github_repo_info"
    return None


def coding_tool_for_prompt(prompt: str) -> str | None:
    normalized = prompt.lower()
    if _is_coding_edit_request(normalized):
        if not _extract_file_path(prompt):
            return None
        if _extract_value(prompt, "old_text") and _extract_value(prompt, "new_text"):
            return "replace_in_file"
        if _extract_value(prompt, "content"):
            return "write_file"
        return "read_file"
    if "replace_in_file" in normalized:
        return "replace_in_file"
    if "write_file" in normalized:
        return "write_file"
    if "run_validation" in normalized:
        return "run_validation"
    if any(keyword in normalized for keyword in ["search_code", "search code", "코드 검색", "전체 코드", "찾아", "검색"]):
        return "search_code"
    if any(keyword in normalized for keyword in ["list_directory", "list directory", "디렉터리 목록", "프로젝트 구조", "구조 보여", "폴더", "directory"]):
        return "list_directory"
    if any(keyword in normalized for keyword in ["read_file", "read file", "파일 읽", "읽어", "파일 분석", "파일 역할", "역할 설명"]):
        return "read_file"
    if _extract_file_path(prompt):
        return "read_file"
    return None


def _is_coding_edit_request(normalized: str) -> bool:
    if any(keyword in normalized for keyword in ["리뷰해줘", "분석해줘", "설명해줘", "review", "analyze", "explain"]):
        return False
    return any(
        keyword in normalized
        for keyword in ["수정해줘", "바꿔줘", "적용해줘", "replace", "update", "edit", "convert this file", "refactor this file"]
    )


def _can_execute_coding_write(prompt: str, path: str) -> bool:
    normalized = prompt.lower()
    has_payload = bool(_extract_value(prompt, "content")) or (
        bool(_extract_value(prompt, "old_text")) and bool(_extract_value(prompt, "new_text"))
    )
    return bool(path) and has_payload and (_is_coding_edit_request(normalized) or "write_file" in normalized or "replace_in_file" in normalized)


def k8s_tool_for_prompt(prompt: str) -> str | None:
    normalized = prompt.lower()
    if not any(keyword in normalized for keyword in ["kubectl", "kubernetes", "쿠버네티스", "pod", "deployment", "service"]):
        return None
    if "logs" in normalized or "log " in f"{normalized} ":
        return "kubectl_logs"
    if "exec" in normalized:
        return "kubectl_exec"
    if "delete" in normalized:
        return "kubectl_delete"
    if "scale" in normalized:
        return "kubectl_scale"
    if "apply" in normalized:
        return "kubectl_apply_file"
    if "rollout restart" in normalized or "restart" in normalized:
        return "kubectl_rollout_restart"
    return None


def docker_tool_for_prompt(prompt: str) -> str | None:
    normalized = prompt.lower()
    if "docker" not in normalized and "compose" not in normalized and "도커" not in normalized:
        return None
    if "compose up" in normalized:
        return "docker_compose_up"
    if "compose down" in normalized:
        return "docker_compose_down"
    if "logs" in normalized or "log " in f"{normalized} ":
        return "docker_logs"
    if "build" in normalized:
        return "docker_build"
    if "run" in normalized:
        return "docker_run"
    if "stop" in normalized:
        return "docker_stop"
    if " rm " in f" {normalized} " or "remove" in normalized:
        return "docker_rm"
    return "get_docker_status"


def _permission_error(tool_name: str, prompt: str) -> str:
    if tool_name in DESTRUCTIVE_TOOLS:
        return f"{tool_name}은(는) 파괴적 작업으로 분류되어 기본 차단되었습니다. 현재 단계에서는 실행하지 않습니다."
    if tool_name in WRITE_TOOLS and not _has_confirmation(prompt):
        return f"{tool_name}은(는) 쓰기 작업입니다. 실행하려면 요청에 confirm=true를 포함해주세요."
    return ""


def permission_result(tool_name: str | None, prompt: str) -> str:
    if not tool_name:
        return "none"
    if tool_name in DESTRUCTIVE_TOOLS:
        return "blocked_destructive"
    if tool_name in WRITE_TOOLS:
        return "allowed_write_confirmed" if _has_confirmation(prompt) else "denied_write_confirmation_required"
    return "allowed_read"


def _has_confirmation(prompt: str) -> bool:
    normalized = prompt.lower()
    return any(flag in normalized for flag in ["confirm=true", "confirmed=true", "allow_write=true"])


def _with_post_write_validation(result: str, path: str, prompt: str) -> str:
    if "Diff:" not in result:
        return result
    result = result + "\n\nGit Diff:\n" + get_git_diff(path)
    if _skips_validation(prompt):
        return result
    commands = _validation_commands_for_path(path)
    if not commands:
        return result
    outputs = [f"$ {command}\n{run_validation(command)}" for command in commands]
    return result + "\n\nValidation:\n" + "\n\n".join(outputs)


def _skips_validation(prompt: str) -> bool:
    normalized = prompt.lower()
    return any(keyword in normalized for keyword in ["검증하지 마", "검증하지마", "no validation", "skip validation"])


def _validation_commands_for_path(path: str) -> list[str]:
    normalized = path.replace("\\", "/").lower()
    commands = []
    if normalized.endswith(".py") or normalized.startswith("backend/"):
        commands.append("pytest")
    if normalized.startswith("frontend/") or normalized in {"package.json", "package-lock.json"}:
        commands.append("npm run build")
    return commands


def _extract_commit_message(prompt: str) -> str:
    match = re.search(r"-m\s+['\"]([^'\"]+)['\"]", prompt)
    if match:
        return match.group(1)
    match = re.search(r"(?:message|메시지|메세지)\s*[:=]\s*['\"]?(.+?)['\"]?$", prompt, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _extract_git_target(prompt: str, action: str) -> str:
    match = re.search(rf"{action}\s+([^\s]+)", prompt, re.IGNORECASE)
    return match.group(1).strip("'\"") if match else ""


def _extract_repo(prompt: str) -> tuple[str, str]:
    match = REPO_PATTERN.search(prompt)
    if not match:
        return "", ""
    return match.groups()


def _extract_value(prompt: str, key: str) -> str:
    match = re.search(rf"{key}\s*=\s*['\"]([^'\"]+)['\"]", prompt, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    match = re.search(rf"{key}\s*=\s*([^\s]+)", prompt, re.IGNORECASE)
    if match:
        return match.group(1).strip("'\"")
    match = re.search(rf"{key}\s*:\s*['\"]?(.+?)['\"]?(?:\s+\w+\s*=|$)", prompt, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _extract_after(prompt: str, marker: str) -> str:
    match = re.search(rf"{re.escape(marker)}\s+([^\s]+)", prompt, re.IGNORECASE)
    return match.group(1).strip("'\"") if match else ""


def _extract_file_path(prompt: str) -> str:
    explicit = _extract_value(prompt, "path") or _extract_after(prompt, "read_file")
    if explicit:
        return explicit
    match = re.search(r"['\"]?([a-zA-Z0-9_.\\/:-]+\.[a-zA-Z0-9_]+)['\"]?", prompt)
    return match.group(1).strip("'\"") if match else ""


def _extract_directory_path(prompt: str) -> str:
    return _extract_value(prompt, "path") or _extract_after(prompt, "list_directory") or "."


def _extract_search_keyword(prompt: str) -> str:
    explicit = _extract_value(prompt, "keyword") or _extract_after(prompt, "search_code")
    if explicit:
        return explicit
    patterns = [
        r"(?:코드에서|에서)\s+([^\s]+)\s+(?:찾|검색)",
        r"(?:find|search)\s+([^\s]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, prompt, re.IGNORECASE)
        if match:
            return match.group(1).strip("'\"")
    return ""


def _extract_kubectl_target(prompt: str, action: str) -> str:
    match = re.search(rf"{action}\s+([a-zA-Z]+/[^\s]+|[^\s]+)", prompt, re.IGNORECASE)
    return match.group(1).strip("'\"") if match else ""


def _extract_docker_build_path(prompt: str) -> str:
    tokens = re.findall(r"['\"][^'\"]+['\"]|\S+", prompt)
    if "build" not in [token.lower() for token in tokens]:
        return "."
    skip_next = False
    candidates: list[str] = []
    for token in tokens[tokens.index(next(token for token in tokens if token.lower() == "build")) + 1 :]:
        clean = token.strip("'\"")
        if skip_next:
            skip_next = False
            continue
        if clean in {"-t", "--tag", "-f", "--file"}:
            skip_next = True
            continue
        if clean.startswith("-"):
            continue
        candidates.append(clean)
    return candidates[-1] if candidates else "."


def _extract_docker_image(prompt: str) -> str:
    tokens = re.findall(r"['\"][^'\"]+['\"]|\S+", prompt)
    lower_tokens = [token.lower() for token in tokens]
    if "run" not in lower_tokens:
        return ""
    skip_next = False
    for token in tokens[lower_tokens.index("run") + 1 :]:
        clean = token.strip("'\"")
        if skip_next:
            skip_next = False
            continue
        if clean in {"--name", "-p", "--publish", "-v", "--volume", "-e", "--env"}:
            skip_next = True
            continue
        if clean in {"-d", "--rm", "-it"} or clean.startswith("-"):
            continue
        return clean
    return ""


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
