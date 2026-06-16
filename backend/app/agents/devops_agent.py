from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from backend.app.agents.prompts import KOREAN_RESPONSE_RULES
from backend.app.config import get_settings
from backend.app.tools.registry import register_devops_tools, route_devops_tool_call


def build_devops_agent(model_name: str | None = None) -> Agent[None, str]:
    settings = get_settings()
    model = OpenAIModel(
        model_name or settings.ollama_model,
        provider=OpenAIProvider(
            base_url=settings.ollama_openai_base_url,
            api_key="ollama",
        ),
    )
    agent = Agent(
        model,
        output_type=str,
        system_prompt=(
            "You are a DevOps-focused local agent. "
            "Use get_git_status for git status questions and get_k8s_pods for Kubernetes pod questions. "
            f"{KOREAN_RESPONSE_RULES}"
        ),
    )
    register_devops_tools(agent)
    return agent


async def run_devops_agent(prompt: str, model_name: str | None = None) -> str:
    routed_result = route_devops_tool_call(prompt)
    if routed_result is not None:
        return routed_result

    agent = build_devops_agent(model_name)
    result = await agent.run(prompt)
    return result.output
