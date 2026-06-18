import pytest

from backend.app.agent import planner
from backend.app.agent.planner import plan_message, plan_message_with_llm


def test_planner_classifies_chat() -> None:
    plan = plan_message("hello")

    assert plan.intent == "chat"
    assert plan.needs_tool is False
    assert plan.target_agent == "chat"


def test_planner_classifies_k8s() -> None:
    plan = plan_message("current kubernetes pod status")

    assert plan.intent == "kubernetes_status"
    assert plan.needs_tool is True
    assert plan.suggested_tool == "get_k8s_pods"
    assert plan.target_agent == "kubernetes"


def test_planner_classifies_file_request() -> None:
    plan = plan_message("show project files")

    assert plan.intent == "file_project_lookup"
    assert plan.needs_tool is True


def test_planner_classifies_code_request() -> None:
    plan = plan_message("explain this code")

    assert plan.intent == "code"
    assert plan.needs_tool is False
    assert plan.target_agent == "coding"


def test_planner_routes_code_patterns_to_coding_before_github() -> None:
    plan = plan_message("이 코드 문제점 알려줘 def divide(a,b): return a/b")

    assert plan.intent == "code"
    assert plan.target_agent == "coding"


def test_planner_classifies_agent_targets() -> None:
    assert plan_message("Docker status").target_agent == "docker"
    assert plan_message("Git status").target_agent == "git"
    assert plan_message("GitHub repo check").target_agent == "github"


def test_planner_detects_specific_command_tools_first() -> None:
    assert plan_message("kubectl logs api-pod").suggested_tool == "kubectl_logs"
    assert plan_message("pod logs api-pod").suggested_tool == "kubectl_logs"
    assert plan_message("존재하지 않는 쿠버네티스 pod 로그 보여줘").suggested_tool == "kubectl_logs"
    assert plan_message("kubectl exec api-pod -- ls").suggested_tool == "kubectl_exec"
    assert plan_message("docker ps").suggested_tool == "get_docker_status"
    assert plan_message("docker logs api").suggested_tool == "docker_logs"
    assert plan_message("git stash").suggested_tool == "git_stash"


@pytest.mark.asyncio
async def test_llm_planner_uses_json_plan(monkeypatch) -> None:
    async def json_planner(prompt: str, model_name: str | None = None) -> str:
        return (
            '{"intent":"git_status","target_agent":"git","required_tools":["get_git_status"],'
            '"steps":["Git status","validate"],"needs_tool":true,"confidence":0.91}'
        )

    monkeypatch.setattr(planner, "run_local_agent", json_planner)

    plan = await plan_message_with_llm(
        "Git status",
        session_id=None,
        available_agents=[],
        available_tools=[{"name": "get_git_status", "enabled": True}],
    )

    assert plan.fallback_used is False
    assert plan.target_agent == "git"
    assert plan.required_tools == ["get_git_status"]


@pytest.mark.asyncio
async def test_llm_planner_falls_back_to_rules(monkeypatch) -> None:
    async def fail_planner(prompt: str, model_name: str | None = None) -> str:
        raise RuntimeError("planner unavailable")

    monkeypatch.setattr(planner, "run_local_agent", fail_planner)

    plan = await plan_message_with_llm(
        "current kubernetes pod status",
        session_id=None,
        available_agents=[],
        available_tools=[],
    )

    assert plan.fallback_used is True
    assert plan.target_agent == "kubernetes"
    assert plan.required_tools == ["get_k8s_pods"]
