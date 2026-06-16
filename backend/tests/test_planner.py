from backend.app.agent.planner import plan_message


def test_planner_classifies_chat() -> None:
    plan = plan_message("안녕")

    assert plan.intent == "chat"
    assert plan.needs_tool is False


def test_planner_classifies_k8s() -> None:
    plan = plan_message("쿠버네티스 pod 상태 알려줘")

    assert plan.intent == "k8s"
    assert plan.needs_tool is True
    assert plan.suggested_tool == "get_k8s_pods"


def test_planner_classifies_file_request() -> None:
    plan = plan_message("프로젝트 파일 구조 확인해줘")

    assert plan.intent == "file"
    assert plan.needs_tool is True


def test_planner_classifies_code_request() -> None:
    plan = plan_message("이 코드 분석해줘")

    assert plan.intent == "code"
    assert plan.needs_tool is False
