import type { AgentActivityStep, AgentInfo, ToolInfo } from '../types/chat';
import { addToolDisplay, isAgentVisibleInUi, isToolVisibleInUi, sortToolsForUi } from '../utils/toolDisplay';

export type ChatRequest = {
  message: string;
  model?: string;
  session_id?: string;
};

export type ChatResponse = {
  answer: string;
};

export type ToolDiscovery = {
  tools: ToolInfo[];
  agents: AgentInfo[];
};

export type ObservabilityMetrics = {
  total_requests: number;
  total_tool_calls: number;
  failed_tool_calls: number;
  average_latency_ms: number;
  last_request_at: string | null;
  last_tool_name: string | null;
};

export type ApiStatus = 'checking' | 'online' | 'offline';

type StreamEvent =
  | ({ type: 'trace' } & AgentActivityStep)
  | { type: 'answer'; answer: string }
  | { type: 'error'; message: string };

export async function checkHealth(apiBaseUrl: string): Promise<boolean> {
  try {
    const response = await fetch(`${apiBaseUrl}/health`);
    if (!response.ok) {
      return false;
    }

    const data = (await response.json()) as { status?: string };
    return data.status === 'ok';
  } catch {
    return false;
  }
}

export async function fetchTools(apiBaseUrl: string): Promise<ToolDiscovery> {
  const response = await fetch(`${apiBaseUrl}/api/tools`);
  if (!response.ok) {
    throw new Error(`도구 목록 요청에 실패했습니다. 상태 코드: ${response.status}`);
  }

  const data = (await response.json()) as { tools?: ToolInfo[]; agents?: AgentInfo[] };
  return {
    tools: sortToolsForUi((data.tools ?? []).filter(isToolVisibleInUi).map(addToolDisplay)),
    agents: sortToolsForUi((data.agents ?? []).filter(isAgentVisibleInUi).map(addToolDisplay)),
  };
}

export async function fetchObservabilityMetrics(apiBaseUrl: string): Promise<ObservabilityMetrics> {
  const response = await fetch(`${apiBaseUrl}/api/observability/metrics`);
  if (!response.ok) {
    throw new Error(`Metrics 요청에 실패했습니다. 상태 코드: ${response.status}`);
  }
  return (await response.json()) as ObservabilityMetrics;
}

export async function clearMemory(apiBaseUrl: string, sessionId: string): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/memory/${encodeURIComponent(sessionId)}`, { method: 'DELETE' });
  if (!response.ok) {
    throw new Error(`Memory 초기화에 실패했습니다. 상태 코드: ${response.status}`);
  }
}

export async function sendChat(
  message: string,
  apiBaseUrl: string,
  modelName?: string,
  sessionId?: string,
): Promise<ChatResponse> {
  const response = await fetch(`${apiBaseUrl}/api/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ message, model: modelName, session_id: sessionId } satisfies ChatRequest),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `요청에 실패했습니다. 상태 코드: ${response.status}`);
  }

  return (await response.json()) as ChatResponse;
}

export async function streamChat(
  message: string,
  apiBaseUrl: string,
  modelName: string,
  sessionId: string,
  onActivity: (step: AgentActivityStep) => void,
): Promise<ChatResponse> {
  const response = await fetch(`${apiBaseUrl}/api/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ message, model: modelName, session_id: sessionId } satisfies ChatRequest),
  });

  if (!response.ok || !response.body) {
    return sendChat(message, apiBaseUrl, modelName, sessionId);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });

    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    for (const line of lines) {
      if (!line.trim()) {
        continue;
      }

      const event = JSON.parse(line) as StreamEvent;
      if (event.type === 'trace') {
        onActivity({
          step: event.step,
          label: event.label,
          description: event.description,
          status: event.status,
          agent: event.agent,
          tool: event.tool,
          metadata: event.metadata,
        });
      } else if (event.type === 'answer') {
        return { answer: event.answer };
      } else if (event.type === 'error') {
        throw new Error(event.message);
      }
    }

    if (done) {
      break;
    }
  }

  throw new Error('에이전트 스트림이 답변 없이 종료되었습니다.');
}
