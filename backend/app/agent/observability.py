from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from threading import Lock
from time import perf_counter
from uuid import uuid4

from backend.app.agent.messages import AgentMessage


MAX_TRACES = 100
SUMMARY_LIMIT = 800


@dataclass
class TraceStep:
    step: str
    status: str
    message: str
    timestamp: str
    duration_ms: float | None = None
    metadata: dict | None = None


@dataclass
class ToolObservation:
    tool_name: str
    status: str
    duration_ms: float
    result_summary: str
    error_message: str | None = None


@dataclass
class RequestTrace:
    request_id: str
    session_id: str
    started_at: str
    status: str = "success"
    duration_ms: float | None = None
    selected_agent: str | None = None
    selected_tool: str | None = None
    steps: list[TraceStep] = field(default_factory=list)
    tool_execution: ToolObservation | None = None
    parallel_tool_executions: list[dict] = field(default_factory=list)
    agent_messages: list[AgentMessage] = field(default_factory=list)


_traces: list[RequestTrace] = []
_started: dict[str, float] = {}
_lock = Lock()
_metrics = {
    "total_requests": 0,
    "total_tool_calls": 0,
    "failed_tool_calls": 0,
    "average_latency_ms": 0.0,
    "last_request_at": None,
    "last_tool_name": None,
}


def begin_trace(session_id: str) -> str:
    request_id = uuid4().hex
    trace = RequestTrace(request_id=request_id, session_id=session_id, started_at=_now())
    trace.steps.append(TraceStep("request_received", "success", "요청을 수신했습니다.", _now()))
    with _lock:
        _started[request_id] = perf_counter()
        _traces.append(trace)
        del _traces[:-MAX_TRACES]
    return request_id


def add_step(
    request_id: str,
    step: str,
    status: str,
    message: str,
    *,
    duration_ms: float | None = None,
    metadata: dict | None = None,
) -> None:
    with _lock:
        trace = _find_trace(request_id)
        if trace:
            trace.steps.append(TraceStep(step, status, message, _now(), duration_ms, metadata))


def set_selection(request_id: str, *, agent: str | None, tool: str | None) -> None:
    with _lock:
        trace = _find_trace(request_id)
        if trace:
            trace.selected_agent = agent
            trace.selected_tool = tool


def record_agent_message(message: AgentMessage) -> None:
    with _lock:
        trace = _find_trace(message.request_id)
        if trace:
            trace.agent_messages.append(message)


def record_tool_execution(
    request_id: str,
    *,
    tool_name: str | None,
    status: str,
    duration_ms: float,
    result: str = "",
    error_message: str | None = None,
) -> None:
    if tool_name is None:
        return
    with _lock:
        trace = _find_trace(request_id)
        if trace:
            trace.tool_execution = ToolObservation(
                tool_name=tool_name,
                status=status,
                duration_ms=round(duration_ms, 2),
                result_summary=_clip(result),
                error_message=error_message,
            )


def record_parallel_tool_executions(request_id: str, results: list[dict]) -> None:
    with _lock:
        trace = _find_trace(request_id)
        if trace:
            trace.parallel_tool_executions = results


def finish_trace(request_id: str, status: str = "success") -> None:
    with _lock:
        trace = _find_trace(request_id)
        started = _started.pop(request_id, None)
        if not trace or started is None:
            return
        duration_ms = round((perf_counter() - started) * 1000, 2)
        trace.status = status
        trace.duration_ms = duration_ms
        _metrics["total_requests"] += 1
        count = _metrics["total_requests"]
        previous = float(_metrics["average_latency_ms"])
        _metrics["average_latency_ms"] = round(previous + (duration_ms - previous) / count, 2)
        _metrics["last_request_at"] = _now()
        if trace.parallel_tool_executions:
            _metrics["total_tool_calls"] += len(trace.parallel_tool_executions)
            _metrics["last_tool_name"] = _recent_tool_name(trace.parallel_tool_executions[-1].get("tool_name"))
            _metrics["failed_tool_calls"] += sum(
                1 for result in trace.parallel_tool_executions if result.get("status") != "success"
            )
        elif trace.tool_execution:
            _metrics["total_tool_calls"] += 1
            _metrics["last_tool_name"] = _recent_tool_name(trace.tool_execution.tool_name)
            if trace.tool_execution.status == "failed":
                _metrics["failed_tool_calls"] += 1


def get_metrics() -> dict:
    with _lock:
        return dict(_metrics)


def list_traces() -> list[dict]:
    with _lock:
        return [_summary(trace) for trace in reversed(_traces)]


def get_trace(request_id: str) -> dict | None:
    with _lock:
        trace = _find_trace(request_id)
        return _trace_dict(trace) if trace else None


def clear_all() -> None:
    with _lock:
        _traces.clear()
        _started.clear()
        _metrics.update(
            total_requests=0,
            total_tool_calls=0,
            failed_tool_calls=0,
            average_latency_ms=0.0,
            last_request_at=None,
            last_tool_name=None,
        )


def _find_trace(request_id: str) -> RequestTrace | None:
    return next((trace for trace in _traces if trace.request_id == request_id), None)


def _summary(trace: RequestTrace) -> dict:
    return {
        "request_id": trace.request_id,
        "session_id": trace.session_id,
        "started_at": trace.started_at,
        "status": trace.status,
        "duration_ms": trace.duration_ms,
        "selected_agent": trace.selected_agent,
        "selected_tool": trace.selected_tool,
        "step_count": len(trace.steps),
    }


def _trace_dict(trace: RequestTrace) -> dict:
    data = asdict(trace)
    data["steps"] = [asdict(step) for step in trace.steps]
    data["tool_execution"] = asdict(trace.tool_execution) if trace.tool_execution else None
    return data


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _clip(text: str) -> str:
    text = text.strip()
    return text if len(text) <= SUMMARY_LIMIT else text[: SUMMARY_LIMIT - 3].rstrip() + "..."


def _recent_tool_name(tool_name: str | None) -> str | None:
    return {
        "get_git_status": "git_status",
        "get_git_branch": "git_branch",
        "get_docker_status": "docker_ps",
    }.get(tool_name or "", tool_name)
