import subprocess


def get_git_status() -> str:
    """Return the current git status using `git status --short`."""

    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "git status timed out after 10 seconds."
    except OSError as exc:
        return f"Failed to run git status: {exc}"

    output = result.stdout.strip()
    error = result.stderr.strip()

    if result.returncode != 0:
        return error or f"git status failed with exit code {result.returncode}."

    return _summarize_status(output)


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
