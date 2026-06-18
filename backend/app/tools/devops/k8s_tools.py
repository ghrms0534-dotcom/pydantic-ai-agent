import subprocess
from collections import defaultdict


CONNECTION_ERROR_MARKERS = (
    "Unable to connect to the server",
    "connectex",
    "couldn't get current server API group list",
)
FAILURE_PREFIX = "Kubernetes 명령 실행에 실패했습니다:"


def _summarize_original_error(error: str) -> str:
    lines = [line.strip() for line in error.splitlines() if line.strip()]
    for line in reversed(lines):
        if "Unable to connect to the server" in line:
            return line
    return lines[-1] if lines else "unknown kubectl error"


def _run_kubectl(args: list[str], timeout: int = 15) -> str:
    command = ["kubectl", *args]
    command_text = " ".join(command)

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return (
            f"{FAILURE_PREFIX}\n"
            f"{command_text} 실행 시간이 초과되었습니다.\n"
            "클러스터 상태 또는 네트워크 연결을 확인하세요."
        )
    except FileNotFoundError:
        return (
            f"{FAILURE_PREFIX}\n"
            "kubectl 명령을 찾을 수 없습니다.\n"
            "kubectl이 설치되어 있고 PATH에 등록되어 있는지 확인하세요."
        )
    except OSError as exc:
        return (
            f"{FAILURE_PREFIX}\n"
            "kubectl 실행 중 오류가 발생했습니다.\n"
            f"원본 오류: {exc}"
        )

    output = result.stdout.strip()
    error = result.stderr.strip()

    if result.returncode != 0:
        if any(marker in error for marker in CONNECTION_ERROR_MARKERS):
            return (
                f"{FAILURE_PREFIX}\n"
                "현재 Kubernetes 클러스터에 연결할 수 없습니다.\n"
                "Docker Desktop 또는 kind cluster가 실행 중인지 확인하세요.\n"
                f"원본 오류: {_summarize_original_error(error)}"
            )

        return (
            f"{FAILURE_PREFIX}\n"
            f"{command_text} 실행에 실패했습니다.\n"
            f"원본 오류: {_summarize_original_error(error)}"
        )

    return output or "조회된 Kubernetes 리소스가 없습니다."


def get_k8s_pods(namespace: str | None = None) -> str:
    """Return Kubernetes pods."""

    if namespace:
        namespace_check = _run_kubectl(["get", "namespace", namespace])
        if namespace_check.startswith(FAILURE_PREFIX):
            if "클러스터에 연결할 수 없습니다" in namespace_check or "kubectl 명령을 찾을 수 없습니다" in namespace_check:
                return namespace_check
            return (
                f"{FAILURE_PREFIX}\n"
                f"{namespace} namespace가 존재하지 않습니다.\n"
                f"원본 오류: {namespace_check}"
            )

    output = _get_k8s_pods_raw(namespace=namespace)
    if output.startswith(FAILURE_PREFIX):
        return output

    if namespace:
        return f"현재 {namespace} namespace의 쿠버네티스 Pod 상태입니다.\n\n{output}"

    return f"현재 쿠버네티스 Pod 상태입니다.\n\n{output}"


def get_k8s_deployments() -> str:
    """Return Kubernetes deployments from all namespaces."""

    output = _run_kubectl(["get", "deployments", "-A"])
    if output.startswith(FAILURE_PREFIX):
        return output
    return f"현재 쿠버네티스 Deployment 상태입니다.\n\n{output}"


def get_k8s_services() -> str:
    """Return Kubernetes services from all namespaces."""

    output = _run_kubectl(["get", "services", "-A"])
    if output.startswith(FAILURE_PREFIX):
        return output
    return f"현재 쿠버네티스 Service 목록입니다.\n\n{output}"


def get_k8s_namespaces() -> str:
    """Return Kubernetes namespaces."""

    output = _run_kubectl(["get", "namespaces"])
    if output.startswith(FAILURE_PREFIX):
        return output
    return f"현재 쿠버네티스 Namespace 목록입니다.\n\n{output}"


def get_k8s_nodes() -> str:
    """Return Kubernetes nodes."""

    output = _run_kubectl(["get", "nodes"])
    if output.startswith(FAILURE_PREFIX):
        return output
    return f"현재 쿠버네티스 Node 상태입니다.\n\n{output}"


def summarize_k8s_pods() -> str:
    """Return a human-readable Korean summary for Kubernetes pods."""

    raw_output = _get_k8s_pods_raw()
    if raw_output.startswith(FAILURE_PREFIX):
        return raw_output

    lines = [line for line in raw_output.splitlines() if line.strip()]
    if len(lines) <= 1:
        return "현재 쿠버네티스 Pod가 조회되지 않았습니다."

    pods_by_namespace: dict[str, list[tuple[str, str]]] = defaultdict(list)
    total = 0
    abnormal: list[str] = []

    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 4:
            continue

        namespace, name, _ready, status = parts[:4]
        total += 1
        pods_by_namespace[namespace].append((name, status))
        if status != "Running":
            abnormal.append(f"{namespace}/{name} {status}")

    if total == 0:
        return "현재 쿠버네티스 Pod가 조회되지 않았습니다."

    summary_lines = [f"총 Pod {total}개가 조회되었습니다.", ""]
    for namespace in sorted(pods_by_namespace):
        summary_lines.append(namespace)
        for name, status in pods_by_namespace[namespace]:
            status_text = "정상" if status == "Running" else status
            summary_lines.append(f"- {name} {status_text}")
        summary_lines.append("")

    if abnormal:
        summary_lines.append("확인이 필요한 Pod:")
        summary_lines.extend(f"- {item}" for item in abnormal)
    else:
        summary_lines.append("전체 Pod가 정상 상태입니다.")

    return "\n".join(summary_lines).strip()


def kubectl_apply_file(path: str) -> str:
    if not path.strip():
        return "kubectl apply -f 실행에는 파일 경로가 필요합니다."
    output = _run_kubectl(["apply", "-f", path], timeout=30)
    return output if output.startswith(FAILURE_PREFIX) else f"kubectl apply 완료입니다.\n\n{output}"


def kubectl_delete(target: str) -> str:
    if not target.strip():
        return "kubectl delete 실행에는 삭제 대상이 필요합니다. 예: pod/name 또는 deployment/name"
    output = _run_kubectl(["delete", *target.split()], timeout=30)
    return output if output.startswith(FAILURE_PREFIX) else f"kubectl delete 완료입니다.\n\n{output}"


def kubectl_scale(target: str, replicas: str) -> str:
    if not target.strip() or not replicas.strip():
        return "kubectl scale 실행에는 대상과 replicas 값이 필요합니다."
    output = _run_kubectl(["scale", target, f"--replicas={replicas}"], timeout=30)
    return output if output.startswith(FAILURE_PREFIX) else f"kubectl scale 완료입니다.\n\n{output}"


def kubectl_rollout_restart(target: str) -> str:
    if not target.strip():
        return "kubectl rollout restart 실행에는 대상이 필요합니다. 예: deployment/app"
    output = _run_kubectl(["rollout", "restart", target], timeout=30)
    return output if output.startswith(FAILURE_PREFIX) else f"kubectl rollout restart 완료입니다.\n\n{output}"


def kubectl_logs(target: str) -> str:
    if not target.strip():
        return "kubectl logs 실행에는 pod 이름이 필요합니다."
    output = _run_kubectl(["logs", target], timeout=30)
    return output if output.startswith(FAILURE_PREFIX) else f"kubectl logs 결과입니다.\n\n{output}"


def kubectl_exec(target: str, command: str) -> str:
    if not target.strip() or not command.strip():
        return "kubectl exec 실행에는 pod 이름과 command가 필요합니다."
    output = _run_kubectl(["exec", target, "--", *command.split()], timeout=30)
    return output if output.startswith(FAILURE_PREFIX) else f"kubectl exec 결과입니다.\n\n{output}"


def _get_k8s_pods_raw(namespace: str | None = None) -> str:
    if namespace:
        return _run_kubectl(["get", "pods", "-n", namespace])

    return _run_kubectl(["get", "pods", "-A"])
