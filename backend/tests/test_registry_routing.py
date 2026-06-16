from backend.app.tools import registry
from backend.app.tools.registry import Intent


def test_classify_general_chat() -> None:
    assert registry.classify_intent("안녕") == Intent.GENERAL_CHAT


def test_classify_kubernetes_knowledge_without_tool_intent() -> None:
    assert registry.classify_intent("쿠버네티스가 무엇인가") == Intent.GENERAL_KNOWLEDGE
    assert registry.has_devops_intent("쿠버네티스가 무엇인가") is False


def test_classify_negated_kubernetes_query_as_knowledge() -> None:
    prompt = "pod 조회하지 말고 쿠버네티스가 뭔지만 설명해줘"
    assert registry.classify_intent(prompt) == Intent.GENERAL_KNOWLEDGE
    assert registry.has_devops_intent(prompt) is False


def test_classify_kubernetes_resource_intents() -> None:
    assert registry.classify_intent("현재 pods 상태 알려줘") == Intent.POD
    assert registry.classify_intent("현재 deployment 상태 알려줘") == Intent.DEPLOYMENT
    assert registry.classify_intent("현재 service 목록 알려줘") == Intent.SERVICE
    assert registry.classify_intent("현재 namespace 목록 알려줘") == Intent.NAMESPACE
    assert registry.classify_intent("현재 node 상태 알려줘") == Intent.NODE
    assert registry.classify_intent("pod 상태 보기 좋게 요약해줘") == Intent.SUMMARY


def test_extract_namespace_from_prompt() -> None:
    assert registry._extract_namespace("default namespace pod 보여줘") == "default"
    assert registry._extract_namespace("kube-system namespace pod 보여줘") == "kube-system"


def test_has_api_intent_for_api_coding_prompt() -> None:
    assert registry.has_api_intent("FastAPI endpoint 하나 만들어줘") is True
    assert registry.has_devops_intent("FastAPI endpoint 하나 만들어줘") is False


def test_explicit_multi_agent_only_when_requested() -> None:
    assert registry.explicitly_requests_multiple_agents("현재 git 상태랑 내 public ip 둘 다 알려줘") is True
    assert registry.explicitly_requests_multiple_agents("현재 pods 상태 알려줘") is False


def test_route_devops_tool_call_uses_namespace(monkeypatch) -> None:
    calls: list[str | None] = []

    def fake_get_k8s_pods(namespace: str | None = None) -> str:
        calls.append(namespace)
        return "NAMESPACE NAME READY STATUS RESTARTS AGE\nkube-system coredns 1/1 Running 0 1m"

    monkeypatch.setattr(registry, "get_k8s_pods", fake_get_k8s_pods)

    assert "coredns" in registry.route_devops_tool_call("kube-system namespace pod 보여줘")
    assert calls == ["kube-system"]


def test_route_devops_tool_call_maps_resource_commands(monkeypatch) -> None:
    monkeypatch.setattr(registry, "get_k8s_deployments", lambda: "deployments")
    monkeypatch.setattr(registry, "get_k8s_services", lambda: "services")
    monkeypatch.setattr(registry, "get_k8s_namespaces", lambda: "namespaces")
    monkeypatch.setattr(registry, "get_k8s_nodes", lambda: "nodes")

    assert registry.route_devops_tool_call("현재 deployment 상태 알려줘") == "deployments"
    assert registry.route_devops_tool_call("현재 service 목록 알려줘") == "services"
    assert registry.route_devops_tool_call("현재 namespace 목록 알려줘") == "namespaces"
    assert registry.route_devops_tool_call("현재 node 상태 알려줘") == "nodes"
