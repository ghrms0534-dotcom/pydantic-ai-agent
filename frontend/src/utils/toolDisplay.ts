import type { AgentInfo, ToolInfo } from '../types/chat';

export type AgentCapability = {
  id: string;
  name: string;
  description: string;
  status: ToolInfo['status'];
};

const displayNames: Record<string, string> = {
  get_git_status: 'Git Agent',
  get_git_branch: 'Git Agent',
  git_add_all: 'Git Agent',
  git_commit: 'Git Agent',
  git_checkout: 'Git Agent',
  git_pull: 'Git Agent',
  git_push: 'Git Agent',
  git_merge: 'Git Agent',
  git_stash: 'Git Agent',
  get_k8s_pods: 'Kubernetes Agent',
  kubectl_apply_file: 'Kubernetes Agent',
  kubectl_delete: 'Kubernetes Agent',
  kubectl_scale: 'Kubernetes Agent',
  kubectl_rollout_restart: 'Kubernetes Agent',
  kubectl_logs: 'Kubernetes Agent',
  kubectl_exec: 'Kubernetes Agent',
  get_github_repo_info: 'GitHub Agent',
  create_github_pull_request: 'GitHub Agent',
  create_github_issue: 'GitHub Agent',
  create_github_release: 'GitHub Agent',
  create_github_branch: 'GitHub Agent',
  github_commit_push: 'GitHub Agent',
  list_project_files: 'File Agent',
  get_memory_status: 'System Agent',
  get_system_status: 'System Agent',
  get_docker_status: 'Docker Agent',
  docker_build: 'Docker Agent',
  docker_run: 'Docker Agent',
  docker_stop: 'Docker Agent',
  docker_rm: 'Docker Agent',
  docker_compose_up: 'Docker Agent',
  docker_compose_down: 'Docker Agent',
  'Orchestrator Agent': 'Chat Agent',
};

const agentOrder = new Map([
  ['Chat Agent', 0],
  ['Coding Agent', 1],
  ['Git Agent', 2],
  ['GitHub Agent', 3],
  ['Kubernetes Agent', 4],
  ['Docker Agent', 5],
  ['File Agent', 6],
  ['System Agent', 7],
]);

const descriptions: Record<string, string> = {
  get_git_status: 'Git 저장소 상태 확인',
  get_git_branch: 'Git branch 확인',
  git_add_all: 'git add . 실행',
  git_commit: 'git commit -m 실행',
  git_checkout: 'git checkout 실행',
  git_pull: 'git pull 실행',
  git_push: 'git push 실행',
  git_merge: 'git merge 실행',
  git_stash: 'git stash 실행',
  get_k8s_pods: 'Kubernetes 리소스 조회',
  kubectl_apply_file: 'kubectl apply -f 실행',
  kubectl_delete: 'kubectl delete 실행',
  kubectl_scale: 'kubectl scale 실행',
  kubectl_rollout_restart: 'kubectl rollout restart 실행',
  kubectl_logs: 'kubectl logs 조회',
  kubectl_exec: 'kubectl exec 실행',
  get_github_repo_info: 'GitHub 저장소 정보 조회',
  create_github_pull_request: 'GitHub pull request 생성',
  create_github_issue: 'GitHub issue 생성',
  create_github_release: 'GitHub release 생성',
  create_github_branch: 'GitHub branch 생성',
  github_commit_push: 'GitHub commit push',
  list_project_files: '프로젝트 파일 목록 조회',
  get_memory_status: 'SQLite Memory 상태 조회',
  get_system_status: '시스템 상태 조회',
  get_docker_status: 'Docker 상태 조회',
  docker_build: 'docker build 실행',
  docker_run: 'docker run 실행',
  docker_stop: 'docker stop 실행',
  docker_rm: 'docker rm 실행',
  docker_compose_up: 'docker compose up 실행',
  docker_compose_down: 'docker compose down 실행',
};

const hiddenToolNames = new Set(['get_public_ip']);
const hiddenAgentNames = new Set(['orchestrator', 'orchestrator agent']);

export const fallbackAgents: AgentInfo[] = [
  fallbackAgent('chat', 'Chat Agent', '일반 대화와 기본 응답', 'active'),
  fallbackAgent('coding', 'Coding Agent', 'Code explanation, review, small fixes, and snippets', 'active'),
  fallbackAgent('git', 'Git Agent', 'Git 저장소 상태 확인', 'inactive'),
  fallbackAgent('github', 'GitHub Agent', 'GitHub 저장소 정보 조회', 'inactive'),
  fallbackAgent('kubernetes', 'Kubernetes Agent', 'Kubernetes 리소스 조회', 'inactive'),
  fallbackAgent('docker', 'Docker Agent', 'Docker 환경 관리', 'inactive'),
  fallbackAgent('file', 'File Agent', '파일과 프로젝트 구조 조회', 'inactive'),
  fallbackAgent('system', 'System Agent', '시스템 상태 조회', 'inactive'),
];

export function isToolVisibleInUi(tool: ToolInfo): boolean {
  return !hiddenToolNames.has(tool.name);
}

export function isAgentVisibleInUi(agent: AgentInfo): boolean {
  return !hiddenAgentNames.has(agent.name.toLowerCase()) && !hiddenAgentNames.has((agent.display_name ?? '').toLowerCase());
}

export function getToolDisplayName(tool: Pick<ToolInfo, 'name' | 'display_name'> | string): string {
  const name = typeof tool === 'string' ? tool : tool.name;
  return typeof tool === 'string' ? displayNames[name] ?? name : tool.display_name ?? displayNames[name] ?? name;
}

export function getAgentDisplayName(agent: string): string {
  return displayNames[agent] ?? agent;
}

export function getToolDescription(tool: ToolInfo): string {
  return descriptions[tool.name] ?? tool.description;
}

export function addToolDisplay(tool: ToolInfo): ToolInfo {
  return {
    ...tool,
    display_name: getToolDisplayName(tool),
    description: getToolDescription(tool),
  };
}

export function localizeToolNames(text: string): string {
  return Object.entries(displayNames).reduce((current, [name, displayName]) => current.replaceAll(name, displayName), text);
}

export function sortToolsForUi(tools: ToolInfo[]): ToolInfo[] {
  return [...tools].sort((left, right) => agentRank(getToolDisplayName(left)) - agentRank(getToolDisplayName(right)));
}

export function getAgentCapabilities(tools: ToolInfo[]): AgentCapability[] {
  return sortToolsForUi(tools).map((tool) =>
    capability(tool.name, getToolDisplayName(tool), getToolDescription(tool), tool.status),
  );
}

function agentRank(agent: string): number {
  return agentOrder.get(getAgentDisplayName(agent)) ?? Number.MAX_SAFE_INTEGER;
}

function capability(
  id: string,
  name: string,
  description: string,
  status: ToolInfo['status'] | undefined,
): AgentCapability {
  return {
    id,
    name,
    description,
    status: status ?? 'inactive',
  };
}

function fallbackAgent(id: string, name: string, description: string, status: ToolInfo['status']): AgentInfo {
  return {
    name: id,
    display_name: name,
    category: 'agent',
    description,
    enabled: status === 'active',
    source: 'agent',
    status,
    detail: 'fallback agent',
  };
}
