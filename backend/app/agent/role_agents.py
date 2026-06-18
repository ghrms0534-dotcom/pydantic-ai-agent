from dataclasses import dataclass
from typing import Any

from backend.app.agent import retry_executor, runner
from backend.app.agent.model_router import select_model
from backend.app.agent.planner import plan_message, plan_message_with_llm
from backend.app.api.schemas import PlannerResult
from backend.app.config import get_settings
from backend.app.tools import registry
from backend.app.tools.validation import ToolValidation, validate_tool_result


PLANNER_AGENT = "Planner Agent"
CHAT_AGENT = "Chat Agent"
CODING_AGENT = "Coding Agent"
DEVOPS_AGENT = "DevOps Agent"
TOOL_AGENT = "Tool Agent"
VALIDATOR_AGENT = "Validator Agent"
SUMMARY_AGENT = "Summary Agent"
FINAL_ANSWER_AGENT = "Final Answer Agent"
CODING_READ_ONLY_TOOLS = {"list_directory", "read_file", "search_code"}
CODING_WRITE_TOOLS = {"write_file", "replace_in_file"}


@dataclass(frozen=True)
class AgentFlow:
    selection_agent: str
    execution_agent: str = TOOL_AGENT
    validation_agent: str = VALIDATOR_AGENT
    summary_agent: str = SUMMARY_AGENT
    planning_model: str = ""
    selection_model: str = ""
    execution_model: str = ""
    validation_model: str = ""
    summary_model: str = ""


@dataclass(frozen=True)
class AgentRunResult:
    answer: str
    raw_answer: str
    flow: AgentFlow
    validation: ToolValidation | None
    tool_agent_skipped: bool = False


class PlannerAgent:
    name = PLANNER_AGENT

    @staticmethod
    def plan(message: str) -> PlannerResult:
        return plan_message(message)

    @staticmethod
    async def plan_async(
        message: str,
        *,
        session_id: str | None,
        available_agents: list[dict],
        available_tools: list[dict],
    ) -> PlannerResult:
        return await plan_message_with_llm(
            message,
            session_id=session_id,
            available_agents=available_agents,
            available_tools=available_tools,
        )


def select_agent_flow(plan: PlannerResult, spawned_agent: Any | None = None) -> AgentFlow:
    selection_agent = {
        "git": "Git Agent",
        "github": "GitHub Agent",
        "kubernetes": "Kubernetes Agent",
        "docker": "Docker Agent",
        "coding": CODING_AGENT,
        "file": "File Agent",
        "system": "System Agent",
    }.get(plan.target_agent, DEVOPS_AGENT if plan.intent in {"k8s", "kubernetes_status", "tool"} and plan.needs_tool else CHAT_AGENT)
    if spawned_agent is not None:
        selection_agent = spawned_agent.display_name
    return AgentFlow(
        selection_agent=selection_agent,
        planning_model=select_model(plan.intent, PLANNER_AGENT, "planning"),
        selection_model=select_model(plan.intent, selection_agent, "selection"),
        execution_model=select_model(plan.intent, TOOL_AGENT, "execution"),
        validation_model=select_model(plan.intent, VALIDATOR_AGENT, "validation"),
        summary_model=select_model(plan.intent, SUMMARY_AGENT, "summary"),
    )


def _validation_failed(answer: str) -> bool:
    if "Validation:" not in answer or "exit_code=" not in answer:
        return False
    validation_text = answer.split("Validation:", 1)[1]
    return "exit_code=0" not in validation_text


async def run_role_agent_flow(
    message: str,
    plan: PlannerResult,
    tool_name: str | None,
    session_id: str | None = None,
    spawned_agent: Any | None = None,
) -> AgentRunResult:
    flow = select_agent_flow(plan, spawned_agent)
    if tool_name is None:
        run_agent = CodingAgent.run if plan.target_agent == "coding" else FinalAnswerAgent.run
        retry = await retry_executor.run_with_retry(
            lambda retry_message: run_agent(retry_message, flow.execution_model),
            message,
            tool_name=tool_name,
            session_id=session_id,
            agent_name=CODING_AGENT if plan.target_agent == "coding" else FINAL_ANSWER_AGENT,
        )
        raw_answer = retry.output
        validation = None if retry.validation.ok else retry.validation
        answer = FinalAnswerAgent.finalize(raw_answer, validation)
        return AgentRunResult(
            answer=answer,
            raw_answer=raw_answer,
            flow=flow,
            validation=validation,
            tool_agent_skipped=True,
        )

    retry = await retry_executor.run_with_retry(
        lambda retry_message: ToolAgent.run_tool(retry_message, tool_name, session_id),
        message,
        tool_name=tool_name,
        session_id=session_id,
        agent_name=TOOL_AGENT,
        max_attempts=1 if tool_name in CODING_WRITE_TOOLS else retry_executor.MAX_ATTEMPTS,
    )
    raw_answer = retry.output
    validation = retry.validation
    if plan.target_agent == "coding" and tool_name in CODING_WRITE_TOOLS and _validation_failed(raw_answer):
        raw_answer = await CodingAgent.self_correct_after_validation_failure(message, tool_name, raw_answer, flow.summary_model, session_id)
        validation = validate_tool_result(raw_answer, tool_name)
    if plan.target_agent == "coding" and tool_name in CODING_READ_ONLY_TOOLS and validation.ok:
        answer = await CodingAgent.summarize_tool_result(message, tool_name, raw_answer, flow.summary_model)
    elif plan.target_agent == "coding" and tool_name in CODING_WRITE_TOOLS:
        answer = raw_answer
    else:
        answer = FinalAnswerAgent.finalize(raw_answer, validation)
    return AgentRunResult(answer=answer, raw_answer=raw_answer, flow=flow, validation=validation)


class ChatAgent:
    name = CHAT_AGENT


class CodingAgent:
    name = CODING_AGENT

    @staticmethod
    async def run(message: str, model_name: str) -> str:
        return await ToolAgent.run(
            (
                "You are Coding Agent. Always answer in Korean. Start with the key problem or answer. "
                "Keep it short and practical. For fixes, output only the necessary code block. "
                "Support code review, bug finding, language conversion, and small examples. "
                "Do not give long theory. Do not claim you ran tests or commands. Do not claim you edited files.\n\n"
                f"{message}"
            ),
            model_name,
        )

    @staticmethod
    async def summarize_tool_result(message: str, tool_name: str, tool_result: str, model_name: str) -> str:
        return await CodingAgent.run(
            (
                "아래 read-only 파일 도구 결과를 바탕으로 사용자 요청에 짧고 실용적으로 답하세요.\n"
                f"사용자 요청:\n{message}\n\n"
                f"실행 도구: {tool_name}\n"
                f"도구 결과:\n{tool_result}"
            ),
            model_name,
        )

    @staticmethod
    async def self_correct_after_validation_failure(message: str, tool_name: str, tool_result: str, model_name: str, session_id: str | None) -> str:
        correction = await CodingAgent.run(
            (
                "파일 수정 후 validation이 실패했습니다. 실패 로그를 보고 수정 가능하면 명령 한 줄만 출력하세요.\n"
                "허용 형식: replace_in_file path=<file> old_text=\"...\" new_text=\"...\" 또는 write_file path=<file> content=\"...\"\n"
                "수정이 불명확하면 NO_FIX만 출력하세요.\n\n"
                f"원래 요청:\n{message}\n\n"
                f"실행 도구: {tool_name}\n"
                f"실패 로그:\n{tool_result}"
            ),
            model_name,
        )
        correction_tool = registry.coding_tool_for_prompt(correction)
        if correction_tool not in CODING_WRITE_TOOLS:
            return tool_result + "\n\nSelf-correction: retry=false\n수정 가능한 자동 보정안을 찾지 못했습니다."
        correction_result = registry.execute_registered_tool(correction_tool, correction, session_id)
        return tool_result + "\n\nSelf-correction: retry=true\n\nCorrection result:\n" + correction_result


class DevOpsAgent:
    name = DEVOPS_AGENT


class ToolAgent:
    name = TOOL_AGENT

    @staticmethod
    async def run(message: str, model_name: str) -> str:
        fallback_model = get_settings().ollama_model
        try:
            return await runner.run_agent(message, model_name=model_name)
        except Exception:
            if model_name == fallback_model:
                raise
            return await runner.run_agent(message)

    @staticmethod
    async def run_tool(message: str, tool_name: str, session_id: str | None) -> str:
        return registry.execute_registered_tool(tool_name, message, session_id)


class ValidatorAgent:
    name = VALIDATOR_AGENT

    @staticmethod
    def validate(answer: str, tool_name: str | None) -> ToolValidation | None:
        if tool_name is None:
            return None
        return validate_tool_result(answer, tool_name)


class FinalAnswerAgent:
    name = FINAL_ANSWER_AGENT

    @staticmethod
    async def run(message: str, model_name: str) -> str:
        return await ToolAgent.run(message, model_name)

    @staticmethod
    def finalize(answer: str, validation: ToolValidation | None) -> str:
        if validation is not None and not validation.ok:
            return validation.message
        return answer


class SummaryAgent(FinalAnswerAgent):
    name = SUMMARY_AGENT
