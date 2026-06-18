import shutil

from backend.app.tools import registry


def _command_status(command: str) -> tuple[str, str]:
    if shutil.which(command):
        return "active", f"{command} found on PATH"
    return "inactive", f"{command} not found on PATH"


def _registered_status() -> tuple[str, str]:
    return "active", "registered in tool registry"


def _status_for(item: registry.RegistryItem) -> tuple[str, str]:
    if item.name.startswith("git_") or item.name in {"get_git_status", "get_git_branch"}:
        return _command_status("git")
    if item.name == "get_docker_status" or item.name.startswith("docker_"):
        return _command_status("docker")
    if item.name.startswith("get_k8s_") or item.name == "summarize_k8s_pods":
        return _command_status("kubectl")
    return _registered_status()


def list_tools() -> list[dict[str, str]]:
    return [_tool_info(item) for item in registry.registered_tools()]


def list_agents() -> list[dict]:
    tools_by_name = {tool["name"]: tool for tool in list_tools()}
    metadata = {
        "chat": ("Chat Agent", "일반 대화와 기본 응답", ["chat"], []),
        "coding": (
            "Coding Agent",
            "Code explanation, review, small fixes, snippets, and project file analysis",
            ["explain_code", "review_code", "minimal_fix", "snippet", "read_file", "search_code", "write_file", "run_validation"],
            ["list_directory", "read_file", "search_code", "write_file", "replace_in_file", "run_validation"],
        ),
        "git": (
            "Git Agent",
            "Git 저장소 상태 확인 및 기본 작업 실행",
            ["git_status", "git_branch", "git_add", "git_commit", "git_checkout", "git_pull", "git_push", "git_merge", "git_stash"],
            ["get_git_status", "get_git_branch", "git_add_all", "git_commit", "git_checkout", "git_pull", "git_push", "git_merge", "git_stash"],
        ),
        "github": (
            "GitHub Agent",
            "GitHub 저장소 정보 조회 및 기본 작업 실행",
            ["github_repo", "github_pr", "github_issue", "github_release", "github_branch", "github_commit_push"],
            [
                "get_github_repo_info",
                "create_github_pull_request",
                "create_github_issue",
                "create_github_release",
                "create_github_branch",
                "github_commit_push",
            ],
        ),
        "kubernetes": (
            "Kubernetes Agent",
            "Kubernetes 리소스 조회",
            ["kubernetes_status", "kubectl_apply", "kubectl_delete", "kubectl_scale", "kubectl_rollout_restart", "kubectl_logs", "kubectl_exec"],
            [
                "get_k8s_pods",
                "get_k8s_deployments",
                "get_k8s_services",
                "get_k8s_namespaces",
                "get_k8s_nodes",
                "kubectl_apply_file",
                "kubectl_delete",
                "kubectl_scale",
                "kubectl_rollout_restart",
                "kubectl_logs",
                "kubectl_exec",
            ],
        ),
        "docker": (
            "Docker Agent",
            "Docker 환경 관리",
            ["docker_status", "docker_logs", "docker_build", "docker_run", "docker_stop", "docker_rm", "docker_compose"],
            [
                "get_docker_status",
                "docker_build",
                "docker_run",
                "docker_logs",
                "docker_stop",
                "docker_rm",
                "docker_compose_up",
                "docker_compose_down",
            ],
        ),
        "file": ("File Agent", "파일과 프로젝트 구조 조회", ["file_project_lookup"], ["list_project_files"]),
        "system": ("System Agent", "시스템 상태 조회", ["system_status", "memory_status"], ["get_memory_status", "get_system_status", "get_public_ip"]),
    }
    return [
        {
            "name": name,
            "display_name": display_name,
            "category": "agent",
            "description": description,
            "capabilities": capabilities,
            "tools": agent_tools,
            "enabled": all(bool(tools_by_name.get(tool, {}).get("enabled", True)) for tool in agent_tools),
            "source": "agent",
            "status": "active",
            "detail": "registered in agent registry",
        }
        for name, (display_name, description, capabilities, agent_tools) in metadata.items()
    ]


def discovery() -> dict[str, list[dict]]:
    return {"tools": list_tools(), "agents": list_agents()}


def _tool_info(item: registry.RegistryItem) -> dict[str, str | bool]:
    status, detail = _status_for(item)
    return {
        "name": item.name,
        "display_name": item.display_name,
        "category": item.category,
        "description": item.description,
        "enabled": status == "active",
        "source": item.source,
        "status": status,
        "detail": detail,
    }
