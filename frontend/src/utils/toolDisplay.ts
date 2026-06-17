import type { AgentInfo, ToolInfo } from '../types/chat';

export type AgentCapability = {
  id: string;
  name: string;
  description: string;
  status: ToolInfo['status'];
};

const displayNames: Record<string, string> = {
  get_git_status: 'Git Agent',
  get_k8s_pods: 'Kubernetes Agent',
  get_github_repo_info: 'GitHub Agent',
  list_project_files: 'File Agent',
  get_memory_status: 'System Agent',
  get_system_status: 'System Agent',
  get_docker_status: 'Docker Agent',
  'Orchestrator Agent': 'Chat Agent',
};

const agentOrder = new Map([
  ['Chat Agent', 0],
  ['Git Agent', 1],
  ['GitHub Agent', 2],
  ['Kubernetes Agent', 3],
  ['Docker Agent', 4],
  ['File Agent', 5],
  ['System Agent', 6],
]);

const descriptions: Record<string, string> = {
  get_git_status: 'Git 저장소 상태 확인',
  get_k8s_pods: 'Kubernetes 리소스 조회',
  get_github_repo_info: 'GitHub 저장소 정보 조회',
  list_project_files: '프로젝트 파일 목록 조회',
  get_memory_status: 'SQLite Memory 상태 조회',
  get_system_status: '시스템 상태 조회',
  get_docker_status: 'Docker 상태 조회',
};

const hiddenToolNames = new Set(['get_public_ip']);
const hiddenAgentNames = new Set(['orchestrator', 'orchestrator agent']);

export const fallbackAgents: AgentInfo[] = [
  fallbackAgent('chat', 'Chat Agent', '일반 대화와 기본 응답', 'active'),
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
