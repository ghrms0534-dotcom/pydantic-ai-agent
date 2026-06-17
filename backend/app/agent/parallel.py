import asyncio
from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Callable

from backend.app.tools.apis.github_api import get_github_repo_info
from backend.app.tools.apis.network_api import get_public_ip
from backend.app.tools.devops.git_tools import get_git_status
from backend.app.tools.devops.k8s_tools import get_k8s_pods
from backend.app.tools.registry import REPO_PATTERN
from backend.app.tools.validation import validate_tool_result


TOOL_TIMEOUT_SECONDS = 20
SUMMARY_LIMIT = 800


@dataclass(frozen=True)
class ParallelToolResult:
    tool_name: str
    status: str
    duration_ms: float
    result_summary: str
    error_message: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


async def run_parallel_tools(message: str, tool_names: list[str]) -> list[ParallelToolResult]:
    return await asyncio.gather(*[_run_tool(message, name) for name in tool_names])


def format_parallel_results(results: list[ParallelToolResult]) -> str:
    lines = ["Parallel tool results:"]
    for result in results:
        lines.append(f"- {result.tool_name}: {result.status}")
        if result.result_summary:
            lines.append(result.result_summary)
        if result.error_message:
            lines.append(f"error: {result.error_message}")
    return "\n".join(lines)


async def _run_tool(message: str, tool_name: str) -> ParallelToolResult:
    started = perf_counter()
    try:
        output = await asyncio.wait_for(asyncio.to_thread(_call_tool, message, tool_name), TOOL_TIMEOUT_SECONDS)
    except TimeoutError:
        return ParallelToolResult(tool_name, "timeout", _elapsed(started), "", "timeout")
    except Exception as exc:
        return ParallelToolResult(tool_name, "failed", _elapsed(started), "", str(exc))

    validation = validate_tool_result(output, tool_name)
    return ParallelToolResult(
        tool_name,
        "success" if validation.ok else "failed",
        _elapsed(started),
        _clip(str(output)),
        None if validation.ok else validation.message,
    )


def _call_tool(message: str, tool_name: str) -> str:
    calls: dict[str, Callable[[], str]] = {
        "get_git_status": get_git_status,
        "get_public_ip": get_public_ip,
        "get_k8s_pods": get_k8s_pods,
    }
    if tool_name == "get_github_repo_info":
        match = REPO_PATTERN.search(message)
        if not match:
            raise ValueError("GitHub repo not found in prompt.")
        owner, repo = match.groups()
        return get_github_repo_info(owner=owner, repo=repo)
    return calls[tool_name]()


def _elapsed(started: float) -> float:
    return round((perf_counter() - started) * 1000, 2)


def _clip(text: str) -> str:
    text = text.strip()
    return text if len(text) <= SUMMARY_LIMIT else text[: SUMMARY_LIMIT - 3].rstrip() + "..."
