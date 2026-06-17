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
DEVOPS_AGENT = "DevOps Agent"
TOOL_AGENT = "Tool Agent"
VALIDATOR_AGENT = "Validator Agent"
SUMMARY_AGENT = "Summary Agent"
FINAL_ANSWER_AGENT = "Final Answer Agent"


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


async def run_role_agent_flow(
    message: str,
    plan: PlannerResult,
    tool_name: str | None,
    session_id: str | None = None,
    spawned_agent: Any | None = None,
) -> AgentRunResult:
    flow = select_agent_flow(plan, spawned_agent)
    if tool_name is None:
        retry = await retry_executor.run_with_retry(
            lambda retry_message: FinalAnswerAgent.run(retry_message, flow.execution_model),
            message,
            tool_name=tool_name,
            session_id=session_id,
            agent_name=FINAL_ANSWER_AGENT,
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
    )
    raw_answer = retry.output
    validation = retry.validation
    answer = FinalAnswerAgent.finalize(raw_answer, validation)
    return AgentRunResult(answer=answer, raw_answer=raw_answer, flow=flow, validation=validation)


class ChatAgent:
    name = CHAT_AGENT


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
