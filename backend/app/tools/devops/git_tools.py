import subprocess

DIFF_LIMIT = 4000


def get_git_status() -> str:
    """Return a Korean summary of `git status --short`."""

    output = _run_git(["status", "--short"], timeout=10)
    if output.startswith("Git 명령"):
        return output
    return _summarize_status(output)


def get_git_branch() -> str:
    return _run_git(["branch", "--show-current"], timeout=10) or "현재 Git branch를 확인할 수 없습니다."


def git_add_all() -> str:
    return _run_git(["add", "."]) or "git add . 완료"


def git_commit(message: str) -> str:
    if not message.strip():
        return 'commit message가 비어 있습니다. 예: git commit -m "message"'
    return _run_git(["commit", "-m", message])


def git_checkout(target: str) -> str:
    if not target.strip():
        return "checkout 대상 branch가 비어 있습니다."
    return _run_git(["checkout", target])


def git_pull() -> str:
    return _run_git(["pull"])


def git_push() -> str:
    return _run_git(["push"])


def git_merge(branch: str) -> str:
    if not branch.strip():
        return "merge 대상 branch가 비어 있습니다."
    return _run_git(["merge", branch])


def git_stash() -> str:
    return _run_git(["stash"])


def get_git_diff(path: str) -> str:
    if not path.strip():
        return "diff를 확인할 파일 경로가 없습니다."
    output = _run_git(["diff", "--", path], timeout=10)
    if not output:
        return "git diff 결과가 없습니다."
    suffix = "\n...diff가 길어 일부만 표시했습니다." if len(output) > DIFF_LIMIT else ""
    return output[:DIFF_LIMIT] + suffix


def _run_git(args: list[str], timeout: int = 30) -> str:
    command = ["git", *args]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return f"Git 명령 시간이 초과되었습니다: {' '.join(command)}"
    except OSError as exc:
        return f"Git 명령 실행 실패: {exc}"

    output = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
    if result.returncode != 0:
        return output or f"Git 명령 실행 실패: {' '.join(command)}"
    return output


def _summarize_status(output: str) -> str:
    if not output:
        return "Git working tree가 깨끗합니다. 커밋되지 않은 변경사항이 없습니다."

    lines = output.splitlines()
    modified = [line[3:] for line in lines if line[:2].strip() == "M"]
    added = [line[3:] for line in lines if line.startswith("A ") or line.startswith("??")]
    deleted = [line[3:] for line in lines if line[:2].strip() == "D"]
    renamed = [line[3:] for line in lines if line[:2].strip() == "R"]
    files = [line[3:] if len(line) > 3 else line for line in lines[:8]]

    summary = [
        "Git 상태 요약입니다.",
        f"- 수정된 파일: {len(modified)}개",
        f"- 새 파일: {len(added)}개",
        f"- 삭제된 파일: {len(deleted)}개",
        f"- 이름 변경 파일: {len(renamed)}개",
        "- 커밋되지 않은 변경사항 있음",
        "",
        "주요 변경 파일:",
        *[f"- {file}" for file in files],
    ]
    return "\n".join(summary)
