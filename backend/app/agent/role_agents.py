from dataclasses import dataclass

from backend.app.agent import runner
from backend.app.agent.model_router import select_model
from backend.app.api.schemas import PlannerResult
from backend.app.config import get_settings
from backend.app.tools.validation import ToolValidation, validate_tool_result


PLANNER_AGENT = "Planner Agent"
CHAT_AGENT = "Chat Agent"
DEVOPS_AGENT = "DevOps Agent"
TOOL_AGENT = "Tool Agent"
VALIDATOR_AGENT = "Validator Agent"
SUMMARY_AGENT = "Summary Agent"


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


def select_agent_flow(plan: PlannerResult) -> AgentFlow:
    selection_agent = DEVOPS_AGENT if plan.intent in {"k8s", "tool"} and plan.needs_tool else CHAT_AGENT
    if plan.intent in {"k8s", "tool"} and plan.needs_tool:
        selection_agent = DEVOPS_AGENT
    return AgentFlow(
        selection_agent=selection_agent,
        planning_model=select_model(plan.intent, PLANNER_AGENT, "planning"),
        selection_model=select_model(plan.intent, selection_agent, "selection"),
        execution_model=select_model(plan.intent, TOOL_AGENT, "execution"),
        validation_model=select_model(plan.intent, VALIDATOR_AGENT, "validation"),
        summary_model=select_model(plan.intent, SUMMARY_AGENT, "summary"),
    )


async def run_role_agent_flow(message: str, plan: PlannerResult, tool_name: str | None) -> AgentRunResult:
    flow = select_agent_flow(plan)
    raw_answer = await ToolAgent.run(message, flow.execution_model)
    validation = ValidatorAgent.validate(raw_answer, tool_name)
    answer = SummaryAgent.finalize(raw_answer, validation)
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


class ValidatorAgent:
    name = VALIDATOR_AGENT

    @staticmethod
    def validate(answer: str, tool_name: str | None) -> ToolValidation | None:
        if tool_name is None:
            return None
        return validate_tool_result(answer, tool_name)


class SummaryAgent:
    name = SUMMARY_AGENT

    @staticmethod
    def finalize(answer: str, validation: ToolValidation | None) -> str:
        if validation is not None and not validation.ok:
            return validation.message
        return answer
