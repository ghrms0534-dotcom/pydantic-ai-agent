import pytest

from backend.app.agent import planner
from backend.app.agent.planner import plan_message, plan_message_with_llm


def test_planner_classifies_chat() -> None:
    plan = plan_message("안녕")

    assert plan.intent == "chat"
    assert plan.needs_tool is False
    assert plan.target_agent == "chat"


def test_planner_classifies_k8s() -> None:
    plan = plan_message("현재 쿠버네티스 pod 상태 알려줘")

    assert plan.intent == "kubernetes_status"
    assert plan.needs_tool is True
    assert plan.suggested_tool == "get_k8s_pods"
    assert plan.target_agent == "kubernetes"


def test_planner_classifies_file_request() -> None:
    plan = plan_message("프로젝트 파일 구조 확인해줘")

    assert plan.intent == "file_project_lookup"
    assert plan.needs_tool is True


def test_planner_classifies_code_request() -> None:
    plan = plan_message("이 코드 분석해줘")

    assert plan.intent == "code"
    assert plan.needs_tool is False


def test_planner_classifies_agent_targets() -> None:
    assert plan_message("Docker 상태 확인해줘").target_agent == "docker"
    assert plan_message("Git 상태 알려줘").target_agent == "git"
    assert plan_message("GitHub repo 확인해줘").target_agent == "github"


@pytest.mark.asyncio
async def test_llm_planner_uses_json_plan(monkeypatch) -> None:
    async def json_planner(prompt: str, model_name: str | None = None) -> str:
        return (
            '{"intent":"git_status","target_agent":"git","required_tools":["get_git_status"],'
            '"steps":["Git 상태 조회","결과 검증"],"needs_tool":true,"confidence":0.91}'
        )

    monkeypatch.setattr(planner, "run_local_agent", json_planner)

    plan = await plan_message_with_llm(
        "Git 상태 알려줘",
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
        "현재 쿠버네티스 pod 상태 알려줘",
        session_id=None,
        available_agents=[],
        available_tools=[],
    )

    assert plan.fallback_used is True
    assert plan.target_agent == "kubernetes"
    assert plan.required_tools == ["get_k8s_pods"]
