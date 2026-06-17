import shutil
import subprocess
from pathlib import Path

from backend.app.agent import memory


ROOT = Path(__file__).resolve().parents[3]


def list_project_files(limit: int = 80) -> str:
    ignored = {".git", ".venv", "node_modules", "dist", "__pycache__", ".tmp"}
    files: list[str] = []
    for path in ROOT.rglob("*"):
        if len(files) >= limit:
            break
        if any(part in ignored for part in path.relative_to(ROOT).parts):
            continue
        if path.is_file():
            files.append(str(path.relative_to(ROOT)).replace("\\", "/"))

    return "현재 프로젝트 파일 목록입니다.\n" + "\n".join(f"- {file}" for file in files)


def get_memory_status(session_id: str | None = None) -> str:
    session = memory.normalize_session_id(session_id)
    conversations = memory.recent_conversations(session, limit=1000)
    memories = memory.list_agent_memory(session)
    traces = memory.list_agent_trace(session)
    return (
        "SQLite Memory 상태입니다.\n"
        f"- session_id: {session}\n"
        f"- 저장된 대화 메시지: {len(conversations)}개\n"
        f"- agent memory: {len(memories)}개\n"
        f"- trace step: {len(traces)}개"
    )


def get_docker_status() -> str:
    if shutil.which("docker") is None:
        return "Docker 상태를 확인할 수 없습니다. docker 명령을 PATH에서 찾지 못했습니다."
    try:
        result = subprocess.run(["docker", "ps", "--format", "table {{.Names}}\t{{.Status}}\t{{.Image}}"], capture_output=True, text=True, timeout=10, check=False)
    except subprocess.TimeoutExpired:
        return "Docker 상태 확인 시간이 초과되었습니다."
    except OSError as exc:
        return f"Docker 상태 확인 중 오류가 발생했습니다: {exc}"

    if result.returncode != 0:
        return result.stderr.strip() or "Docker 상태 확인에 실패했습니다."
    output = result.stdout.strip()
    return "현재 Docker 실행 상태입니다.\n" + (output or "실행 중인 컨테이너가 없습니다.")


def get_system_status() -> str:
    total, used, free = shutil.disk_usage(ROOT)
    gb = 1024**3
    return (
        "시스템 상태 요약입니다.\n"
        f"- 프로젝트 경로: {ROOT}\n"
        f"- 디스크 전체: {total / gb:.1f}GB\n"
        f"- 디스크 사용: {used / gb:.1f}GB\n"
        f"- 디스크 여유: {free / gb:.1f}GB"
    )
