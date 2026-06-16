from typing import Any

from backend.app.agent.language_guard import (
    contains_awkward_mixed_language,
    contains_blocked_cjk,
    ensure_natural_korean_answer,
)
from backend.app.agent.output_guard import (
    build_raw_output_fallback,
    build_summarize_prompt,
    looks_like_raw_tool_output,
    stringify_tool_result,
)
from backend.app.agents.local_agent import run_local_agent


RETRY_KOREAN_ONLY_INSTRUCTION = (
    "주의: 방금 답변에 중국어 또는 일본어가 섞였다. "
    "이번 답변은 반드시 자연스러운 한국어로만 작성해."
)
RETRY_NATURAL_KOREAN_INSTRUCTION = (
    "주의: 방금 답변에 어색한 한영 혼합 표현이 섞였다. "
    "기술 고유명사를 제외하고 이번 답변은 자연스러운 한국어 문장으로만 다시 작성해."
)


async def _call_agent_once(message: str, model_name: str | None = None) -> Any:
    return await run_local_agent(message, model_name)


async def _call_agent(message: str, model_name: str | None = None) -> Any:
    if model_name is None:
        return await _call_agent_once(message)
    return await _call_agent_once(message, model_name)


async def _summarize_raw_output_once(message: str, raw_output: str, model_name: str | None = None) -> str:
    summarize_prompt = build_summarize_prompt(original_message=message, raw_output=raw_output)
    return stringify_tool_result(await _call_agent(summarize_prompt, model_name))


async def _ensure_not_raw_output(message: str, answer: str, model_name: str | None = None) -> str:
    if not looks_like_raw_tool_output(answer):
        return answer

    try:
        summarized_answer = _clean_answer(await _summarize_raw_output_once(message, answer, model_name))
    except Exception:
        return build_raw_output_fallback(answer)

    if not summarized_answer or looks_like_raw_tool_output(summarized_answer):
        return build_raw_output_fallback(answer)

    return summarized_answer


async def _ensure_korean_only(message: str, answer: str, model_name: str | None = None) -> str:
    if not contains_blocked_cjk(answer) and not contains_awkward_mixed_language(answer):
        return answer

    instruction = (
        RETRY_KOREAN_ONLY_INSTRUCTION
        if contains_blocked_cjk(answer)
        else RETRY_NATURAL_KOREAN_INSTRUCTION
    )
    retry_message = f"{message}\n\n{instruction}"
    retry_answer = _clean_answer(await _call_agent(retry_message, model_name))
    return ensure_natural_korean_answer(retry_answer)


def _clean_answer(answer: Any) -> str:
    return stringify_tool_result(answer).strip()


async def run_agent(message: str, model_name: str | None = None) -> str:
    answer = _clean_answer(await _call_agent(message, model_name))
    answer = await _ensure_not_raw_output(message, answer, model_name)
    return await _ensure_korean_only(message, answer, model_name)
