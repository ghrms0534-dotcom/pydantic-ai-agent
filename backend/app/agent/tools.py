import shutil

from backend.app.tools import registry


def _command_status(command: str) -> tuple[str, str]:
    if shutil.which(command):
        return "active", f"{command} found on PATH"
    return "inactive", f"{command} not found on PATH"


def _registered_status() -> tuple[str, str]:
    return "active", "registered in tool registry"


def _status_for(item: registry.RegistryItem) -> tuple[str, str]:
    if item.name == "get_git_status":
        return _command_status("git")
    if item.name == "get_docker_status":
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
        "git": ("Git Agent", "Git 저장소 상태 확인", ["git_status"], ["get_git_status"]),
        "github": ("GitHub Agent", "GitHub 저장소 정보 조회", ["github_repo"], ["get_github_repo_info"]),
        "kubernetes": (
            "Kubernetes Agent",
            "Kubernetes 리소스 조회",
            ["kubernetes_status"],
            ["get_k8s_pods", "get_k8s_deployments", "get_k8s_services", "get_k8s_namespaces", "get_k8s_nodes"],
        ),
        "docker": ("Docker Agent", "Docker 환경 상태 확인", ["docker_status"], ["get_docker_status"]),
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
