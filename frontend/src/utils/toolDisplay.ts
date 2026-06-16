import type { ToolInfo } from '../types/chat';

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
};

const descriptions: Record<string, string> = {
  get_git_status: 'Git 저장소 상태 확인',
  get_k8s_pods: 'Kubernetes 리소스 조회',
  get_github_repo_info: 'GitHub 저장소 정보 조회',
};

const hiddenToolNames = new Set(['get_public_ip']);

export function isToolVisibleInUi(tool: ToolInfo): boolean {
  return !hiddenToolNames.has(tool.name);
}

export function getToolDisplayName(tool: Pick<ToolInfo, 'name' | 'display_name'> | string): string {
  const name = typeof tool === 'string' ? tool : tool.name;
  return typeof tool === 'string' ? displayNames[name] ?? name : tool.display_name ?? displayNames[name] ?? name;
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
  return Object.entries(displayNames).reduce(
    (current, [name, displayName]) => current.replaceAll(name, displayName),
    text,
  );
}

export function getAgentCapabilities(tools: ToolInfo[]): AgentCapability[] {
  const byName = new Map(tools.map((tool) => [tool.name, tool]));

  return [
    capability('git', 'Git Agent', 'Git 저장소 상태 확인', byName.get('get_git_status')?.status),
    capability('kubernetes', 'Kubernetes Agent', 'Kubernetes 리소스 조회', byName.get('get_k8s_pods')?.status),
    capability('github', 'GitHub Agent', 'GitHub 저장소 정보 조회', byName.get('get_github_repo_info')?.status),
    capability('docker', 'Docker Agent', 'Docker 환경 관리', 'inactive'),
  ];
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
