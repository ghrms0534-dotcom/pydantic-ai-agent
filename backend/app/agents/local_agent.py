from pydantic_ai import Agent

from backend.app.agents.orchestrator_agent import build_orchestrator_agent, run_orchestrator_agent


def build_local_agent(model_name: str | None = None) -> Agent[None, str]:
    return build_orchestrator_agent(model_name)


async def run_local_agent(prompt: str, model_name: str | None = None) -> str:
    return await run_orchestrator_agent(prompt, model_name)
