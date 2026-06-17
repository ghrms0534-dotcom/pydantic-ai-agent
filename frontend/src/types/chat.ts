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
  step?:
    | 'memory_load'
    | 'tool_discovery'
    | 'planner_agent'
    | 'agent_message_sent'
    | 'parallel_execution_decision'
    | 'parallel_tool_execution_start'
    | 'parallel_tool_execution_end'
    | 'planning'
    | 'tool_selection'
    | 'tool_agent'
    | 'tool_execution'
    | 'validator_agent'
    | 'validation'
    | 'final_answer_agent'
    | 'final_answer'
    | 'memory_save';
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
  enabled?: boolean;
  source?: 'builtin' | 'mcp' | 'agent' | string;
  status: 'active' | 'inactive' | 'error';
  detail: string;
};

export type AgentInfo = ToolInfo;

export type DashboardSettings = {
  apiBaseUrl: string;
  agentName: string;
  modelName: string;
  theme: 'light' | 'dark';
};
