import socket
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from backend.app.agent import memory
from backend.app.config import get_settings


QUEUE_NAME = "maos:agent_tasks"
TASK_STATUSES = {"pending", "running", "success", "failed"}


def enqueue_task(agent_name: str, payload: dict[str, Any], session_id: str | None) -> str:
    task_id = uuid4().hex
    memory.create_task(task_id, session_id, agent_name, payload)
    memory.save_agent_trace(session_id, "Orchestrator Agent", "task_enqueued", agent_name, task_id)
    _redis_command("LPUSH", QUEUE_NAME, task_id)
    return task_id


def get_task_status(task_id: str) -> dict | None:
    return memory.get_task(task_id)


def update_task_status(task_id: str, status: str, result: str = "", error: str = "") -> dict:
    if status not in TASK_STATUSES:
        raise ValueError(f"invalid task status: {status}")
    return memory.update_task(task_id, status, result, error)


def list_session_tasks(session_id: str | None) -> list[dict]:
    return memory.list_tasks(session_id)


def pop_task(timeout_seconds: int = 5) -> str | None:
    response = _redis_command("BRPOP", QUEUE_NAME, str(timeout_seconds))
    if isinstance(response, list) and len(response) == 2:
        return str(response[1])
    return None


def _redis_command(*parts: str) -> Any:
    parsed = urlparse(get_settings().redis_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6379
    db = (parsed.path or "/0").lstrip("/") or "0"
    with socket.create_connection((host, port), timeout=3) as connection:
        if db != "0":
            connection.sendall(_encode("SELECT", db))
            _read_response(connection)
        connection.sendall(_encode(*parts))
        return _read_response(connection)


def _encode(*parts: str) -> bytes:
    payload = [f"*{len(parts)}\r\n"]
    for part in parts:
        data = part.encode()
        payload.append(f"${len(data)}\r\n")
        payload.append(data.decode())
        payload.append("\r\n")
    return "".join(payload).encode()


def _read_response(connection: socket.socket) -> Any:
    prefix = connection.recv(1)
    if prefix == b"+":
        return _read_line(connection)
    if prefix == b":":
        return int(_read_line(connection))
    if prefix == b"$":
        length = int(_read_line(connection))
        if length < 0:
            return None
        data = _read_exact(connection, length)
        _read_exact(connection, 2)
        return data.decode()
    if prefix == b"*":
        count = int(_read_line(connection))
        return [_read_response(connection) for _ in range(count)]
    if prefix == b"-":
        raise RuntimeError(_read_line(connection))
    raise RuntimeError("invalid redis response")


def _read_line(connection: socket.socket) -> str:
    chunks = []
    while True:
        char = connection.recv(1)
        if char == b"\r":
            connection.recv(1)
            return b"".join(chunks).decode()
        chunks.append(char)


def _read_exact(connection: socket.socket, length: int) -> bytes:
    data = b""
    while len(data) < length:
        data += connection.recv(length - len(data))
    return data
