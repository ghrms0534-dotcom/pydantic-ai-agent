from backend.app.tools.validation import run_with_validation_retry, validate_tool_result


POD_OUTPUT = """NAMESPACE   NAME      READY   STATUS    RESTARTS   AGE
default     api-123   1/1     Running   0          1m
"""


def test_validate_normal_kubectl_pod_output() -> None:
    validation = validate_tool_result(POD_OUTPUT, "get_k8s_pods")

    assert validation.ok is True
    assert validation.reason == "ok"


def test_validate_empty_output() -> None:
    validation = validate_tool_result("", "get_k8s_pods")

    assert validation.ok is False
    assert validation.reason == "empty"
    assert validation.message == "결과가 비어 있습니다."


def test_validate_kubectl_error_string() -> None:
    validation = validate_tool_result("Error from server (Forbidden): pods is forbidden", "get_k8s_pods")

    assert validation.ok is False
    assert validation.reason == "permission_denied"
    assert validation.message == "권한 문제로 조회하지 못했습니다."


def test_validation_retry_returns_clear_message_after_second_failure() -> None:
    calls = 0

    def call() -> str:
        nonlocal calls
        calls += 1
        return ""

    result, validation = run_with_validation_retry("get_k8s_pods", call)

    assert calls == 2
    assert result == "결과가 비어 있습니다."
    assert validation.ok is False
    assert validation.reason == "empty"
