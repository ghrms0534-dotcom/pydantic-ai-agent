import difflib
import shlex
import shutil
import subprocess
from pathlib import Path

from backend.app.agent import memory


ROOT = Path(__file__).resolve().parents[3]
IGNORED_DIRS = {".git", ".venv", "node_modules", "dist", "build", "__pycache__", ".tmp"}
SENSITIVE_FILE_MARKERS = {".env", "secret", "key", "token", "credential"}
READ_LIMIT = 12000
SEARCH_LIMIT = 50
VALIDATION_TIMEOUT = 120
ALLOWED_VALIDATION_COMMANDS = {
    ("pytest",),
    ("python", "-m", "pytest"),
    ("npm", "run", "build"),
    ("npm", "test"),
    ("npm", "run", "lint"),
}
BANNED_VALIDATION_TOKENS = {"rm", "del", "curl", "wget", "powershell", "sudo", "kubectl", "docker"}


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


def list_directory(path: str = ".") -> str:
    target, error = _safe_project_path(path or ".")
    if error:
        return error
    if not target.exists():
        return "경로가 존재하지 않습니다."
    if not target.is_dir():
        return "디렉터리가 아닙니다."

    entries = []
    for item in sorted(target.iterdir(), key=lambda entry: (not entry.is_dir(), entry.name.lower())):
        if item.name in IGNORED_DIRS or _is_sensitive_path(item):
            continue
        entries.append(f"- {item.name}{'/' if item.is_dir() else ''}")
    label = "." if target == ROOT.resolve() else target.relative_to(ROOT.resolve()).as_posix()
    return f"{label} 디렉터리 목록입니다.\n" + ("\n".join(entries) or "비어 있습니다.")


def read_file(path: str) -> str:
    target, error = _safe_project_path(path)
    if error:
        return error
    if _is_sensitive_path(target):
        return "민감 정보 파일은 읽을 수 없습니다."
    if not target.exists():
        return "파일이 존재하지 않습니다."
    if not target.is_file():
        return "파일이 아닙니다."
    if _is_binary_file(target):
        return "바이너리 파일은 읽을 수 없습니다."
    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return "텍스트 파일만 읽을 수 있습니다."
    clipped = text[:READ_LIMIT]
    suffix = "\n...파일이 길어 일부만 표시했습니다." if len(text) > READ_LIMIT else ""
    return f"{target.relative_to(ROOT.resolve()).as_posix()} 파일 내용입니다.\n\n{clipped}{suffix}"


def search_code(keyword: str) -> str:
    if not keyword:
        return "검색어를 입력해주세요."
    results: list[str] = []
    lowered = keyword.lower()
    for path in ROOT.rglob("*"):
        if len(results) >= SEARCH_LIMIT:
            break
        relative = path.relative_to(ROOT)
        if any(part in IGNORED_DIRS for part in relative.parts):
            continue
        if _is_sensitive_path(path):
            continue
        if not path.is_file() or path.stat().st_size > READ_LIMIT * 20 or _is_binary_file(path):
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(lines, 1):
            if lowered in line.lower():
                results.append(f"{relative.as_posix()}:{number}: {line.strip()[:160]}")
                break
    return f"'{keyword}' 검색 결과입니다.\n" + ("\n".join(results) or "검색 결과가 없습니다.")


def write_file(path: str, content: str) -> str:
    if not path:
        return "파일 경로가 없어 수정하지 않았습니다."
    target, error = _safe_project_path(path)
    if error:
        return error
    if "\0" in (content or ""):
        return "텍스트 파일만 수정할 수 있습니다."
    error = _write_error(target)
    if error:
        return error
    old_text = ""
    if target.exists():
        try:
            old_text = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return "텍스트 파일만 수정할 수 있습니다."
    target.write_text(content or "", encoding="utf-8")
    return _format_write_result(target, old_text, content or "")


def replace_in_file(path: str, old_text: str, new_text: str) -> str:
    if not path:
        return "파일 경로가 없어 수정하지 않았습니다."
    target, error = _safe_project_path(path)
    if error:
        return error
    if "\0" in (old_text or "") or "\0" in (new_text or ""):
        return "텍스트 파일만 수정할 수 있습니다."
    error = _write_error(target)
    if error:
        return error
    if not target.exists() or not target.is_file():
        return "수정할 파일이 존재하지 않습니다."
    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return "텍스트 파일만 수정할 수 있습니다."
    count = text.count(old_text or "")
    if count != 1:
        return f"old_text 매칭 수가 {count}개라 수정하지 않았습니다."
    new_content = text.replace(old_text, new_text, 1)
    target.write_text(new_content, encoding="utf-8")
    return _format_write_result(target, text, new_content)


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


def _safe_project_path(path: str) -> tuple[Path, str]:
    if not path:
        return ROOT.resolve(), ""
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    resolved = candidate.resolve()
    try:
        relative = resolved.relative_to(ROOT.resolve())
    except ValueError:
        return resolved, "프로젝트 root 밖 경로는 접근할 수 없습니다."
    if any(part in IGNORED_DIRS for part in relative.parts):
        return resolved, "제외된 디렉터리는 조회할 수 없습니다."
    return resolved, ""


def _is_sensitive_path(path: Path) -> bool:
    lowered = path.name.lower()
    return any(marker in lowered for marker in SENSITIVE_FILE_MARKERS)


def _write_error(path: Path) -> str:
    if _is_sensitive_path(path):
        return "민감 정보 파일은 수정할 수 없습니다."
    if path.exists() and (not path.is_file() or _is_binary_file(path)):
        return "텍스트 파일만 수정할 수 있습니다."
    if not path.parent.exists():
        return "상위 디렉터리가 존재하지 않아 수정할 수 없습니다."
    return ""


def _format_write_result(path: Path, before: str, after: str) -> str:
    relative = path.relative_to(ROOT.resolve()).as_posix()
    diff = "\n".join(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile=f"{relative}:before",
            tofile=f"{relative}:after",
            lineterm="",
        )
    )
    return f"{relative} 파일을 수정했습니다.\n\nDiff:\n{diff or '(변경 없음)'}"


def _is_binary_file(path: Path) -> bool:
    try:
        return b"\0" in path.read_bytes()[:4096]
    except OSError:
        return True


def get_docker_status() -> str:
    output = _run_docker(["ps", "--format", "table {{.Names}}\t{{.Status}}\t{{.Image}}"])
    return "현재 Docker 실행 상태입니다.\n" + (output or "실행 중인 컨테이너가 없습니다.")


def docker_build(path: str = ".", tag: str = "") -> str:
    args = ["build"]
    if tag:
        args.extend(["-t", tag])
    args.append(path or ".")
    return "Docker build 실행 결과입니다.\n" + _run_docker(args, timeout=120)


def docker_run(image: str, name: str = "", detach: bool = True) -> str:
    if not image:
        return "Docker run을 실행하려면 image 값을 입력해주세요."
    args = ["run"]
    if detach:
        args.append("-d")
    if name:
        args.extend(["--name", name])
    args.append(image)
    return "Docker run 실행 결과입니다.\n" + _run_docker(args, timeout=60)


def docker_logs(container: str) -> str:
    if not container:
        return "Docker logs를 실행하려면 container 값이 필요합니다."
    return "Docker logs 실행 결과입니다.\n" + _run_docker(["logs", container], timeout=30)


def docker_stop(container: str) -> str:
    if not container:
        return "Docker stop을 실행하려면 container 값을 입력해주세요."
    return "Docker stop 실행 결과입니다.\n" + _run_docker(["stop", container], timeout=30)


def docker_rm(container: str) -> str:
    if not container:
        return "Docker rm을 실행하려면 container 값을 입력해주세요."
    return "Docker rm 실행 결과입니다.\n" + _run_docker(["rm", container], timeout=30)


def docker_compose_up(detach: bool = True) -> str:
    args = ["compose", "up"]
    if detach:
        args.append("-d")
    return "Docker compose up 실행 결과입니다.\n" + _run_docker(args, timeout=120)


def docker_compose_down() -> str:
    return "Docker compose down 실행 결과입니다.\n" + _run_docker(["compose", "down"], timeout=60)


def run_validation(command: str) -> str:
    try:
        args = tuple(shlex.split(command or "", posix=False))
    except ValueError as exc:
        return f"검증 명령 파싱 실패: {exc}"
    if not args:
        return "검증 명령을 입력해주세요."
    lower_args = tuple(arg.lower() for arg in args)
    banned_pairs = {("pip", "install"), ("npm", "install"), ("git", "push"), ("git", "commit")}
    if set(lower_args) & BANNED_VALIDATION_TOKENS or any(pair in zip(lower_args, lower_args[1:]) for pair in banned_pairs):
        return "허용되지 않은 검증 명령입니다."
    if lower_args not in ALLOWED_VALIDATION_COMMANDS:
        return "허용된 검증 명령만 실행할 수 있습니다."
    if shutil.which(args[0]) is None:
        return f"{args[0]} 명령을 PATH에서 찾을 수 없습니다."
    try:
        result = subprocess.run(list(args), cwd=ROOT.resolve(), capture_output=True, text=True, timeout=VALIDATION_TIMEOUT, check=False)
    except subprocess.TimeoutExpired as exc:
        return f"exit_code=timeout\nstdout:\n{exc.stdout or ''}\nstderr:\n{exc.stderr or ''}"
    except OSError as exc:
        return f"exit_code=error\nstderr:\n{exc}"
    return f"exit_code={result.returncode}\nstdout:\n{result.stdout.strip()}\nstderr:\n{result.stderr.strip()}"


def _run_docker(args: list[str], timeout: int = 10) -> str:
    if shutil.which("docker") is None:
        return "Docker 명령을 PATH에서 찾지 못했습니다."
    try:
        result = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return "Docker 명령 실행 시간이 초과되었습니다."
    except OSError as exc:
        return f"Docker 명령 실행 중 오류가 발생했습니다: {exc}"

    output = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
    if result.returncode != 0:
        return output or "Docker 명령 실행에 실패했습니다."
    return output or "Docker 명령이 완료되었습니다."


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
