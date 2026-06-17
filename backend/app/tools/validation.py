from dataclasses import dataclass
from typing import Any


KUBECTL_ERROR_MARKERS = (
    "error from server",
    "notfound",
    "forbidden",
    "connection refused",
    "timeout",
    "unable to connect",
    "kubernetes 명령 실행에 실패했습니다",
)
POD_STATUS_MARKERS = ("running", "pending", "error", "crashloopbackoff", "completed", "failed")
GENERIC_ERROR_MARKERS = ("exception", "traceback", "failed", "timeout")


@dataclass(frozen=True)
class ToolValidation:
    ok: bool
    reason: str
    message: str


def validate_tool_result(result: Any, tool_name: str | None = None) -> ToolValidation:
    text = _stringify_result(result)
    lowered = text.lower()

    if not text.strip():
        return _fail("empty", "결과가 비어 있습니다.")

    if isinstance(result, dict):
        error_value = result.get("stderr") or result.get("error")
        if error_value:
            return _classify_error(str(error_value))

    marker_error = _first_marker(lowered)
    if marker_error:
        return _classify_error(text)

    if "error" in lowered or any(marker in lowered for marker in GENERIC_ERROR_MARKERS):
        return _fail("error", "요청 처리 중 오류가 발생했습니다. 입력이나 실행 환경을 확인해주세요.")

    if tool_name == "get_k8s_pods" and not _looks_like_pod_output(lowered):
        return _fail("unexpected_kubectl_format", "예상한 kubectl 출력 형식이 아닙니다.")

    if "결과가 비어 있습니다" in text:
        return _fail("empty", "결과가 비어 있습니다.")
    if "클러스터 연결 실패" in text:
        return _fail("cluster_connection_failed", "클러스터 연결 실패로 보입니다.")
    if "권한 문제" in text:
        return _fail("permission_denied", "권한 문제로 조회하지 못했습니다.")
    if "예상한 kubectl 출력 형식이 아닙니다" in text:
        return _fail("unexpected_kubectl_format", "예상한 kubectl 출력 형식이 아닙니다.")

    return ToolValidation(ok=True, reason="ok", message="검증을 통과했습니다.")


def run_with_validation_retry(tool_name: str, call) -> tuple[str, ToolValidation]:
    first_result = call()
    first_validation = validate_tool_result(first_result, tool_name)
    if first_validation.ok:
        return first_result, first_validation

    second_result = call()
    second_validation = validate_tool_result(second_result, tool_name)
    if second_validation.ok:
        return second_result, second_validation

    return second_validation.message, second_validation


def _stringify_result(result: Any) -> str:
    if result is None:
        return ""
    if isinstance(result, dict):
        return "\n".join(str(value) for value in result.values() if value is not None)
    return str(result)


def _first_marker(lowered: str) -> str | None:
    return next((marker for marker in KUBECTL_ERROR_MARKERS if marker in lowered), None)


def _classify_error(text: str) -> ToolValidation:
    lowered = text.lower()
    if "forbidden" in lowered:
        return _fail("permission_denied", "권한 문제로 조회하지 못했습니다.")
    if "unable to connect" in lowered or "connection refused" in lowered:
        return _fail("cluster_connection_failed", "클러스터 연결 실패로 보입니다.")
    if "timeout" in lowered:
        return _fail("timeout", "클러스터 연결 실패로 보입니다.")
    return _fail("kubectl_error", "클러스터 연결 실패로 보입니다.")


def _looks_like_pod_output(lowered: str) -> bool:
    has_header = all(header in lowered for header in ("name", "ready", "status"))
    has_status = any(status in lowered for status in POD_STATUS_MARKERS)
    return has_header or has_status


def _fail(reason: str, message: str) -> ToolValidation:
    return ToolValidation(ok=False, reason=reason, message=message)
