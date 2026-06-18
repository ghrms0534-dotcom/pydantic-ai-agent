from base64 import b64encode
from os import environ
from typing import Any

import httpx


def get_github_repo_info(owner: str, repo: str) -> str:
    """Return public GitHub repository info for the given owner and repo."""

    data = _github_request("GET", f"/repos/{owner}/{repo}")
    if isinstance(data, str):
        return data
    return "\n".join(
        [
            f"full_name: {data.get('full_name')}",
            f"stars: {data.get('stargazers_count')}",
            f"forks: {data.get('forks_count')}",
            f"default_branch: {data.get('default_branch')}",
            f"html_url: {data.get('html_url')}",
        ]
    )


def create_github_pull_request(owner: str, repo: str, title: str, head: str, base: str = "main", body: str = "") -> str:
    if not title or not head:
        return 'PR 생성에는 title과 head branch가 필요합니다. 예: GitHub owner/repo pr title="..." head=feature base=main'
    data = _github_request("POST", f"/repos/{owner}/{repo}/pulls", {"title": title, "head": head, "base": base, "body": body})
    return _created("Pull Request", data)


def create_github_issue(owner: str, repo: str, title: str, body: str = "") -> str:
    if not title:
        return 'Issue 생성에는 title이 필요합니다. 예: GitHub owner/repo issue title="..."'
    data = _github_request("POST", f"/repos/{owner}/{repo}/issues", {"title": title, "body": body})
    return _created("Issue", data)


def create_github_release(owner: str, repo: str, tag_name: str, name: str = "", body: str = "") -> str:
    if not tag_name:
        return 'Release 생성에는 tag가 필요합니다. 예: GitHub owner/repo release tag=v1.0.0'
    data = _github_request("POST", f"/repos/{owner}/{repo}/releases", {"tag_name": tag_name, "name": name or tag_name, "body": body})
    return _created("Release", data)


def create_github_branch(owner: str, repo: str, branch: str, from_branch: str = "main") -> str:
    if not branch:
        return 'Branch 생성에는 branch 이름이 필요합니다. 예: GitHub owner/repo branch name=feature'
    source = _github_request("GET", f"/repos/{owner}/{repo}/git/ref/heads/{from_branch}")
    if isinstance(source, str):
        return source
    sha = source.get("object", {}).get("sha")
    data = _github_request("POST", f"/repos/{owner}/{repo}/git/refs", {"ref": f"refs/heads/{branch}", "sha": sha})
    return _created("Branch", data)


def github_commit_push(owner: str, repo: str, path: str, content: str, message: str, branch: str = "main") -> str:
    if not path or not content or not message:
        return 'Commit push에는 path, content, message가 필요합니다. 예: GitHub owner/repo commit path=README.md message="update" content="..."'
    data = _github_request(
        "PUT",
        f"/repos/{owner}/{repo}/contents/{path}",
        {"message": message, "content": b64encode(content.encode()).decode(), "branch": branch},
    )
    return _created("Commit", data.get("commit", data) if isinstance(data, dict) else data)


def _github_request(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any] | str:
    try:
        response = httpx.request(
            method,
            f"https://api.github.com{path}",
            headers=_headers(),
            json=payload,
            follow_redirects=True,
            timeout=10.0,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return f"GitHub API returned {exc.response.status_code}."
    except httpx.HTTPError as exc:
        return f"Failed to request GitHub API: {exc}"
    return response.json()


def _headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json"}
    token = environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _created(label: str, data: dict[str, Any] | str) -> str:
    if isinstance(data, str):
        return data
    return f"{label} 생성 완료: {data.get('html_url') or data.get('url') or data.get('ref') or data.get('sha')}"
