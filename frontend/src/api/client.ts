import type { AgentActivityStep, ToolInfo } from '../types/chat';
import { addToolDisplay, isToolVisibleInUi } from '../utils/toolDisplay';

export type ChatRequest = {
  message: string;
  model?: string;
};

export type ChatResponse = {
  answer: string;
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

export async function fetchTools(apiBaseUrl: string): Promise<ToolInfo[]> {
  const response = await fetch(`${apiBaseUrl}/tools`);
  if (!response.ok) {
    throw new Error(`도구 목록 요청에 실패했습니다. 상태 코드: ${response.status}`);
  }

  const data = (await response.json()) as { tools?: ToolInfo[] };
  return (data.tools ?? []).filter(isToolVisibleInUi).map(addToolDisplay);
}

export async function sendChat(message: string, apiBaseUrl: string, modelName?: string): Promise<ChatResponse> {
  const response = await fetch(`${apiBaseUrl}/api/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ message, model: modelName } satisfies ChatRequest),
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
  onActivity: (step: AgentActivityStep) => void,
): Promise<ChatResponse> {
  const response = await fetch(`${apiBaseUrl}/api/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ message, model: modelName } satisfies ChatRequest),
  });

  if (!response.ok || !response.body) {
    return sendChat(message, apiBaseUrl, modelName);
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
