export type ChatRole = 'user' | 'agent';

export type ChatMessage = {
  id: string;
  role: ChatRole;
  content: string;
};

export type ChatSession = {
  id: string;
  title: string;
  messages: ChatMessage[];
  updatedAt: number;
};

export type AgentActivityStep = {
  step?: 'planning' | 'tool_selection' | 'tool_execution' | 'validation' | 'final_answer';
  label: string;
  description: string;
  status?: 'pending' | 'active' | 'complete' | 'error';
  agent?: string;
  tool?: string;
  metadata?: Record<string, unknown>;
};

export type ToolInfo = {
  name: string;
  display_name?: string;
  category: string;
  description: string;
  status: 'active' | 'inactive' | 'error';
  detail: string;
};

export type DashboardSettings = {
  apiBaseUrl: string;
  agentName: string;
  modelName: string;
  theme: 'light' | 'dark';
};
