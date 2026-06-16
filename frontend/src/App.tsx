import { useEffect, useMemo, useState } from 'react';

import { ApiStatus, checkHealth, fetchTools, streamChat } from './api/client';
import { ChatConsole } from './components/ChatConsole';
import { Header } from './components/Header';
import { RightPanel } from './components/RightPanel';
import { Sidebar, type SidebarView } from './components/Sidebar';
import { defaultSettings, starterMessages } from './data/dashboard';
import type { AgentActivityStep, ChatMessage, ChatSession, DashboardSettings, ToolInfo } from './types/chat';

const SETTINGS_KEY = 'pydantic-ai-dashboard:settings';
const SESSIONS_KEY = 'pydantic-ai-dashboard:sessions';
const CURRENT_SESSION_KEY = 'pydantic-ai-dashboard:current-session';

function createSession(): ChatSession {
  return {
    id: crypto.randomUUID(),
    title: '새 대화',
    messages: starterMessages,
    updatedAt: Date.now(),
  };
}

function loadSettings(): DashboardSettings {
  try {
    return { ...defaultSettings, ...JSON.parse(localStorage.getItem(SETTINGS_KEY) ?? '{}') };
  } catch {
    return defaultSettings;
  }
}

function loadSessions(): ChatSession[] {
  try {
    const sessions = JSON.parse(localStorage.getItem(SESSIONS_KEY) ?? '[]') as ChatSession[];
    return sessions.length > 0 ? sessions : [createSession()];
  } catch {
    return [createSession()];
  }
}

function titleFromMessages(messages: ChatMessage[]): string {
  const firstUserMessage = messages.find((message) => message.role === 'user');
  return firstUserMessage?.content.slice(0, 42) || '새 대화';
}

function App() {
  const [settings, setSettings] = useState<DashboardSettings>(() => loadSettings());
  const [apiStatus, setApiStatus] = useState<ApiStatus>('checking');
  const [sessions, setSessions] = useState<ChatSession[]>(() => loadSessions());
  const [currentSessionId, setCurrentSessionId] = useState(() => {
    const storedSessionId = localStorage.getItem(CURRENT_SESSION_KEY);
    return sessions.some((session) => session.id === storedSessionId) ? storedSessionId ?? '' : sessions[0]?.id ?? '';
  });
  const [activeView, setActiveView] = useState<SidebarView>('trace');
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [toolsError, setToolsError] = useState<string | null>(null);
  const [activity, setActivity] = useState<AgentActivityStep[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const currentSession = useMemo(
    () => sessions.find((session) => session.id === currentSessionId) ?? sessions[0],
    [currentSessionId, sessions],
  );
  const messages = currentSession?.messages ?? starterMessages;
  const recentAgent = getRecentAgent(activity);

  useEffect(() => {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
    document.documentElement.classList.toggle('dark', settings.theme === 'dark');
  }, [settings]);

  useEffect(() => {
    localStorage.setItem(SESSIONS_KEY, JSON.stringify(sessions));
  }, [sessions]);

  useEffect(() => {
    if (currentSessionId) {
      localStorage.setItem(CURRENT_SESSION_KEY, currentSessionId);
    }
  }, [currentSessionId]);

  useEffect(() => {
    let mounted = true;
    setApiStatus('checking');
    setToolsError(null);

    checkHealth(settings.apiBaseUrl).then((ok) => {
      if (mounted) {
        setApiStatus(ok ? 'online' : 'offline');
      }
    });

    fetchTools(settings.apiBaseUrl)
      .then((nextTools) => {
        if (mounted) {
          setTools(nextTools);
        }
      })
      .catch((requestError) => {
        if (mounted) {
          setTools([]);
          setToolsError(requestError instanceof Error ? requestError.message : '도구 목록을 불러오지 못했습니다.');
        }
      });

    return () => {
      mounted = false;
    };
  }, [settings.apiBaseUrl]);

  function updateCurrentSession(nextMessages: ChatMessage[]) {
    setSessions((current) =>
      current.map((session) =>
        session.id === currentSessionId
          ? {
              ...session,
              title: titleFromMessages(nextMessages),
              messages: nextMessages,
              updatedAt: Date.now(),
            }
          : session,
      ),
    );
  }

  async function handleSend() {
    const message = input.trim();
    if (!message || loading) {
      return;
    }

    setActiveView('trace');
    setInput('');
    setError(null);
    setLoading(true);
    setActivity([
      { label: '요청 수신', description: '사용자 메시지를 대화에 추가했습니다.', status: 'complete' },
      { label: '백엔드 API 호출', description: `${settings.apiBaseUrl}/api/chat/stream`, status: 'active' },
    ]);

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: message,
    };
    const nextMessages = [...messages, userMessage];
    updateCurrentSession(nextMessages);

    try {
      const response = await streamChat(message, settings.apiBaseUrl, settings.modelName, (step) => {
        setActivity((current) => [...current, step]);
      });
      const agentMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'agent',
        content: response.answer,
      };
      updateCurrentSession([...nextMessages, agentMessage]);
      setActivity((current) => [
        ...current,
        { label: '응답 수신', description: '백엔드가 에이전트 응답을 반환했습니다.', status: 'complete' },
        { label: '요청 완료', description: '대화가 브라우저 기록에 저장되었습니다.', status: 'complete' },
      ]);
    } catch (requestError) {
      const text = requestError instanceof Error ? requestError.message : '에이전트 요청에 실패했습니다.';
      setError(text);
      setActivity((current) => [...current, { label: '요청 실패', description: text, status: 'error' }]);
    } finally {
      setLoading(false);
    }
  }

  function handleNewChat() {
    const session = createSession();
    setSessions((current) => [session, ...current]);
    setCurrentSessionId(session.id);
    setInput('');
    setError(null);
    setActivity([]);
  }

  function handleRestoreSession(sessionId: string) {
    setCurrentSessionId(sessionId);
    setInput('');
    setError(null);
  }

  function handleDeleteSession(sessionId: string) {
    setSessions((current) => {
      const remaining = current.filter((session) => session.id !== sessionId);
      if (sessionId !== currentSessionId) {
        return remaining;
      }

      const nextSession = remaining[0] ?? createSession();
      setCurrentSessionId(nextSession.id);
      setInput('');
      setError(null);
      setActivity([]);
      return remaining.length > 0 ? remaining : [nextSession];
    });
  }

  function handleClearSessions() {
    const session = createSession();
    setSessions([session]);
    setCurrentSessionId(session.id);
    setInput('');
    setError(null);
    setActivity([]);
  }

  return (
    <div className="app-bg flex h-screen overflow-hidden">
      <div className="flex min-h-0 w-full flex-col">
        <Header apiStatus={apiStatus} settings={settings} toolsLoaded={tools.length} />
        <div className="grid min-h-0 flex-1 grid-cols-[240px_minmax(0,1fr)_280px]">
          <Sidebar
            activeView={activeView}
            sessions={sessions}
            currentSessionId={currentSessionId}
            settings={settings}
            tools={tools}
            activity={activity}
            toolsError={toolsError}
            onViewChange={setActiveView}
            onNewChat={handleNewChat}
            onRestoreSession={handleRestoreSession}
            onDeleteSession={handleDeleteSession}
            onClearSessions={handleClearSessions}
            onSettingsChange={setSettings}
          />
          <ChatConsole
            messages={messages}
            input={input}
            loading={loading}
            error={error}
            tools={tools}
            onInputChange={setInput}
            onSend={() => void handleSend()}
          />
          <RightPanel settings={settings} tools={tools} recentAgent={recentAgent} />
        </div>
      </div>
    </div>
  );
}

export default App;

function getRecentAgent(activity: AgentActivityStep[]): string {
  const selected = [...activity].reverse().find((step) => step.step === 'tool_selection');
  if (!selected) {
    return 'Chat Agent';
  }
  if (selected.tool === 'get_git_status') {
    return 'Git Agent';
  }
  if (selected.tool?.includes('k8s')) {
    return 'Kubernetes Agent';
  }
  if (selected.tool === 'get_github_repo_info') {
    return 'GitHub Agent';
  }
  return selected.agent === 'DevOps Agent' ? 'Kubernetes Agent' : selected.agent ?? 'Chat Agent';
}
