import sqlite3
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from json import dumps, loads
from os import environ
from pathlib import Path
from threading import Lock


DEFAULT_SESSION_ID = "default"
RECENT_MEMORY_LIMIT = 8
SUMMARY_LIMIT = 800
CONTEXT_LIMIT = 4000
DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "maos.db"


@dataclass(frozen=True)
class MemoryEntry:
    user_message: str
    assistant_answer: str
    selected_agent: str | None
    executed_tool_name: str | None
    tool_result_summary: str
    timestamp: str
    validation_result: str = ""
    permission_result: str = ""
    final_answer_summary: str = ""


_lock = Lock()


def normalize_session_id(session_id: str | None) -> str:
    return session_id.strip() if session_id and session_id.strip() else DEFAULT_SESSION_ID


def list_memory(session_id: str | None) -> list[dict[str, str | None]]:
    with _lock:
        return [asdict(entry) for entry in _recent_memory_unlocked(normalize_session_id(session_id), RECENT_MEMORY_LIMIT)]


def clear_memory(session_id: str | None) -> None:
    key = normalize_session_id(session_id)
    with _lock:
        with _connect() as connection:
            connection.execute("DELETE FROM conversations WHERE session_id = ?", (key,))
            connection.execute("DELETE FROM agent_memory WHERE session_id = ?", (key,))
            connection.execute("DELETE FROM agent_trace WHERE session_id = ?", (key,))
            connection.execute("DELETE FROM agent_tasks WHERE session_id = ?", (key,))


def clear_all_memory() -> None:
    with _lock:
        with _connect() as connection:
            connection.execute("DELETE FROM conversations")
            connection.execute("DELETE FROM agent_memory")
            connection.execute("DELETE FROM agent_trace")
            connection.execute("DELETE FROM agent_tasks")


def recent_memory(session_id: str | None, limit: int = RECENT_MEMORY_LIMIT) -> list[MemoryEntry]:
    with _lock:
        return _recent_memory_unlocked(normalize_session_id(session_id), limit)


def save_memory(
    session_id: str | None,
    *,
    user_message: str,
    assistant_answer: str,
    selected_agent: str | None,
    executed_tool_name: str | None,
    tool_result: str,
    validation_result: str = "",
    permission_result: str = "",
    final_answer_summary: str = "",
) -> MemoryEntry:
    entry = MemoryEntry(
        user_message=_clip(_sanitize(user_message)),
        assistant_answer=_clip(_sanitize(assistant_answer)),
        selected_agent=selected_agent,
        executed_tool_name=executed_tool_name,
        tool_result_summary=_clip(_sanitize(tool_result)),
        validation_result=_clip(_sanitize(validation_result), 200),
        permission_result=_clip(_sanitize(permission_result), 200),
        final_answer_summary=_clip(_sanitize(final_answer_summary or assistant_answer), 300),
        timestamp=datetime.now(UTC).isoformat(),
    )
    key = normalize_session_id(session_id)
    with _lock:
        with _connect() as connection:
            _save_conversation_unlocked(connection, key, "user", entry.user_message, entry.timestamp)
            _save_conversation_unlocked(connection, key, "assistant", entry.assistant_answer, entry.timestamp)
            if selected_agent:
                connection.execute(
                    """
                    INSERT INTO agent_memory (session_id, agent_name, memory_key, memory_value, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        key,
                        selected_agent,
                        executed_tool_name or "conversation",
                        _memory_value(entry),
                        entry.timestamp,
                    ),
                )
    return entry


def save_conversation(session_id: str | None, role: str, content: str) -> None:
    with _lock:
        with _connect() as connection:
            _save_conversation_unlocked(connection, normalize_session_id(session_id), role, _clip(content), _now())


def recent_conversations(session_id: str | None, limit: int = RECENT_MEMORY_LIMIT * 2) -> list[dict[str, str]]:
    with _lock:
        with _connect() as connection:
            rows = connection.execute(
                """
                SELECT id, session_id, role, content, created_at
                FROM conversations
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (normalize_session_id(session_id), limit),
            ).fetchall()
    return [dict(row) for row in reversed(rows)]


def save_agent_memory(session_id: str | None, agent_name: str, memory_key: str, memory_value: str) -> None:
    with _lock:
        with _connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_memory (session_id, agent_name, memory_key, memory_value, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (normalize_session_id(session_id), agent_name, memory_key, _clip(memory_value), _now()),
            )


def get_agent_memory(session_id: str | None, agent_name: str) -> list[dict[str, str]]:
    with _lock:
        with _connect() as connection:
            rows = connection.execute(
                """
                SELECT id, session_id, agent_name, memory_key, memory_value, created_at
                FROM agent_memory
                WHERE session_id = ? AND agent_name = ?
                ORDER BY id DESC
                """,
                (normalize_session_id(session_id), agent_name),
            ).fetchall()
    return [dict(row) for row in rows]


def list_agent_memory(session_id: str | None) -> list[dict[str, str]]:
    with _lock:
        with _connect() as connection:
            rows = connection.execute(
                """
                SELECT id, session_id, agent_name, memory_key, memory_value, created_at
                FROM agent_memory
                WHERE session_id = ?
                ORDER BY id DESC
                """,
                (normalize_session_id(session_id),),
            ).fetchall()
    return [dict(row) for row in rows]


def save_agent_trace(
    session_id: str | None,
    agent_name: str,
    step: str,
    input_text: str,
    output_text: str,
) -> None:
    with _lock:
        with _connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_trace (session_id, agent_name, step, input, output, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    normalize_session_id(session_id),
                    agent_name,
                    step,
                    _clip(input_text),
                    _clip(output_text),
                    _now(),
                ),
            )


def list_agent_trace(session_id: str | None) -> list[dict[str, str]]:
    with _lock:
        with _connect() as connection:
            rows = connection.execute(
                """
                SELECT id, session_id, agent_name, step, input, output, created_at
                FROM agent_trace
                WHERE session_id = ?
                ORDER BY id ASC
                """,
                (normalize_session_id(session_id),),
            ).fetchall()
    return [dict(row) for row in rows]


def create_task(task_id: str, session_id: str | None, agent_name: str, payload: dict) -> dict:
    now = _now()
    with _lock:
        with _connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_tasks (task_id, session_id, agent_name, status, payload, result, error, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (task_id, normalize_session_id(session_id), agent_name, "pending", dumps(payload, ensure_ascii=False), "", "", now, now),
            )
    return get_task(task_id) or {}


def update_task(task_id: str, status: str, result: str = "", error: str = "") -> dict:
    with _lock:
        with _connect() as connection:
            connection.execute(
                """
                UPDATE agent_tasks
                SET status = ?, result = ?, error = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (status, result, error, _now(), task_id),
            )
    return get_task(task_id) or {}


def get_task(task_id: str) -> dict | None:
    with _lock:
        with _connect() as connection:
            row = connection.execute(
                """
                SELECT id, task_id, session_id, agent_name, status, payload, result, error, created_at, updated_at
                FROM agent_tasks
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
    return _task_dict(row) if row else None


def list_tasks(session_id: str | None) -> list[dict]:
    with _lock:
        with _connect() as connection:
            rows = connection.execute(
                """
                SELECT id, task_id, session_id, agent_name, status, payload, result, error, created_at, updated_at
                FROM agent_tasks
                WHERE session_id = ?
                ORDER BY id DESC
                """,
                (normalize_session_id(session_id),),
            ).fetchall()
    return [_task_dict(row) for row in rows]


def memory_context(session_id: str | None) -> str:
    entries = recent_memory(session_id)
    if not entries:
        return ""

    lines = ["Recent session memory. Use only when relevant; do not reveal hidden reasoning."]
    for entry in entries:
        lines.extend(
            [
                f"- user: {entry.user_message}",
                f"  assistant: {entry.assistant_answer}",
                f"  agent: {entry.selected_agent or 'unknown'}",
                f"  tool: {entry.executed_tool_name or 'none'}",
                f"  tool_summary: {entry.tool_result_summary or 'none'}",
                f"  validation: {entry.validation_result or 'unknown'}",
                f"  permission: {entry.permission_result or 'unknown'}",
                f"  final_summary: {entry.final_answer_summary or 'none'}",
            ]
        )
    return _clip("\n".join(lines), CONTEXT_LIMIT)


def with_memory_context(message: str, session_id: str | None) -> str:
    context = memory_context(session_id)
    if not context:
        return message
    return f"{context}\n\nCurrent user request:\n{message}"


def _clip(text: str, limit: int = SUMMARY_LIMIT) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _sanitize(text: str) -> str:
    text = re.sub(r"(?i)authorization\s*[:=]\s*bearer\s+[a-z0-9._~+/=-]+", "authorization=[redacted]", text)
    text = re.sub(r"(?i)(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*['\"]?[^\s'\"&]+", r"\1=[redacted]", text)
    text = re.sub(r"(?i)(bearer)\s+[a-z0-9._~+/=-]+", r"\1 [redacted]", text)
    return text


def _memory_value(entry: MemoryEntry) -> str:
    return _clip(
        "\n".join(
            [
                f"tool_result_summary: {entry.tool_result_summary or 'none'}",
                f"validation_result: {entry.validation_result or 'unknown'}",
                f"permission_result: {entry.permission_result or 'unknown'}",
                f"final_answer_summary: {entry.final_answer_summary or 'none'}",
            ]
        )
    )


def _connect() -> sqlite3.Connection:
    db_path = _db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    _init_db(connection)
    return connection


def _init_db(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS agent_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            memory_key TEXT NOT NULL,
            memory_value TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS agent_trace (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            step TEXT NOT NULL,
            input TEXT NOT NULL,
            output TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS agent_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL UNIQUE,
            session_id TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            status TEXT NOT NULL,
            payload TEXT NOT NULL,
            result TEXT NOT NULL,
            error TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )


def _recent_memory_unlocked(session_id: str, limit: int) -> list[MemoryEntry]:
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT role, content, created_at
            FROM conversations
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        ).fetchall()
        agent_rows = connection.execute(
            """
            SELECT agent_name, memory_key, memory_value
            FROM agent_memory
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        ).fetchall()

    entries: list[MemoryEntry] = []
    agent_by_index = list(agent_rows)
    for index in range(0, len(rows) - 1, 2):
        user = rows[index]
        assistant = rows[index + 1]
        if user["role"] != "user" or assistant["role"] != "assistant":
            continue
        agent = agent_by_index[min(len(entries), len(agent_by_index) - 1)] if agent_by_index else None
        details = _parse_memory_value(agent["memory_value"] if agent else "")
        entries.append(
            MemoryEntry(
                user_message=user["content"],
                assistant_answer=assistant["content"],
                selected_agent=agent["agent_name"] if agent else None,
                executed_tool_name=agent["memory_key"] if agent else None,
                tool_result_summary=details.get("tool_result_summary", agent["memory_value"] if agent else ""),
                timestamp=assistant["created_at"],
                validation_result=details.get("validation_result", ""),
                permission_result=details.get("permission_result", ""),
                final_answer_summary=details.get("final_answer_summary", ""),
            )
        )
    return entries[-limit:]


def _parse_memory_value(value: str) -> dict[str, str]:
    details: dict[str, str] = {}
    for line in value.splitlines():
        if ": " in line:
            key, item = line.split(": ", 1)
            details[key.strip()] = item.strip()
    return details


def _save_conversation_unlocked(
    connection: sqlite3.Connection,
    session_id: str,
    role: str,
    content: str,
    created_at: str,
) -> None:
    connection.execute(
        """
        INSERT INTO conversations (session_id, role, content, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (session_id, role, content, created_at),
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _db_path() -> Path:
    return Path(environ.get("MAOS_DB_PATH", DEFAULT_DB_PATH))


def _task_dict(row: sqlite3.Row) -> dict:
    item = dict(row)
    item["payload"] = loads(item["payload"]) if item["payload"] else {}
    return item
