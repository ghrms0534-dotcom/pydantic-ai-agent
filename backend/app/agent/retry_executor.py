import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from backend.app.agent import memory
from backend.app.tools.validation import ToolValidation, validate_tool_result


MAX_ATTEMPTS = 2
TIMEOUT_SECONDS = 45


@dataclass(frozen=True)
class RetryResult:
    output: str
    validation: ToolValidation
    attempts: int


async def run_with_retry(
    call: Callable[[str], Awaitable[str]],
    message: str,
    *,
    tool_name: str | None,
    session_id: str | None,
    agent_name: str,
    max_attempts: int = MAX_ATTEMPTS,
    timeout_seconds: int = TIMEOUT_SECONDS,
) -> RetryResult:
    current_message = message
    last_validation = validate_tool_result("", tool_name)
    last_output = ""

    for attempt in range(1, max_attempts + 1):
        try:
            output = await asyncio.wait_for(call(current_message), timeout_seconds)
        except TimeoutError:
            output = "timeout"
        except Exception as exc:
            output = f"{type(exc).__name__}: {exc}"

        last_output = "" if output is None else str(output)
        last_validation = validate_tool_result(last_output, tool_name)
        _save_trace(session_id, agent_name, f"retry_attempt_{attempt}", current_message, last_output)

        if last_validation.ok:
            _save_trace(session_id, agent_name, "retry_success", current_message, last_output)
            return RetryResult(last_output, last_validation, attempt)

        _save_trace(
            session_id,
            agent_name,
            "retry_validation_failed",
            current_message,
            last_validation.message,
        )
        current_message = f"{message}\n\nCorrection hint: {_correction_hint(last_validation.reason)}"

    _save_trace(session_id, agent_name, "retry_failed", current_message, last_validation.message)
    return RetryResult(_friendly_failure(last_validation), last_validation, max_attempts)


def _save_trace(session_id: str | None, agent_name: str, step: str, input_text: str, output_text: str) -> None:
    if session_id is not None:
        memory.save_agent_trace(session_id, agent_name, step, input_text, output_text)


def _correction_hint(reason: str) -> str:
    hints = {
        "empty": "previous result was empty; retry with a broader, simpler query.",
        "timeout": "previous request timed out; retry with a shorter request.",
        "unexpected_kubectl_format": "previous output format was invalid; request plain command output.",
    }
    return hints.get(reason, "previous attempt failed; re-check command, input, and available context.")


def _friendly_failure(validation: ToolValidation) -> str:
    return validation.message or "요청을 다시 시도했지만 완료하지 못했습니다. 입력이나 실행 환경을 확인해주세요."
