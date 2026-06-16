import { AlertCircle, CheckCircle2, Circle, Plus, Trash2, X } from 'lucide-react';

import { navigationItems } from '../data/dashboard';
import type { AgentActivityStep, ChatSession, DashboardSettings, ToolInfo } from '../types/chat';
import { getToolDescription, getToolDisplayName, localizeToolNames } from '../utils/toolDisplay';

export type SidebarView = 'tools' | 'trace' | 'history' | 'settings';

type SidebarProps = {
  activeView: SidebarView;
  sessions: ChatSession[];
  currentSessionId: string;
  settings: DashboardSettings;
  tools: ToolInfo[];
  activity: AgentActivityStep[];
  toolsError: string | null;
  onViewChange: (view: SidebarView) => void;
  onNewChat: () => void;
  onRestoreSession: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => void;
  onClearSessions: () => void;
  onSettingsChange: (settings: DashboardSettings) => void;
};

export function Sidebar({
  activeView,
  sessions,
  currentSessionId,
  settings,
  tools,
  activity,
  toolsError,
  onViewChange,
  onNewChat,
  onRestoreSession,
  onDeleteSession,
  onClearSessions,
  onSettingsChange,
}: SidebarProps) {
  return (
    <aside className="surface flex min-h-0 flex-col border-r p-4">
      <button
        className="primary-btn mb-4 flex h-10 shrink-0 items-center justify-center gap-2 rounded text-sm font-medium"
        onClick={onNewChat}
      >
        <Plus size={17} aria-hidden="true" />
        새 대화
      </button>

      <nav className="shrink-0 space-y-1">
        {navigationItems.map((item) => {
          const Icon = item.icon;
          const isActive = item.id === activeView;
          return (
            <button
              key={item.id}
              className={`flex h-10 w-full items-center gap-3 rounded px-3 text-sm ${
                isActive ? 'nav-item-active' : 'nav-item'
              }`}
              onClick={() => onViewChange(item.id as SidebarView)}
            >
              <Icon size={17} aria-hidden="true" />
              {item.label}
            </button>
          );
        })}
      </nav>

      <section className="mt-4 min-h-0 flex-1 border-t border-line pt-4 dark:border-slate-800">
        {activeView === 'trace' && <ActivityPanel activity={activity} />}
        {activeView === 'tools' && <ToolsPanel tools={tools} error={toolsError} />}
        {activeView === 'history' && (
          <HistoryPanel
            sessions={sessions}
            currentSessionId={currentSessionId}
            onRestoreSession={onRestoreSession}
            onDeleteSession={onDeleteSession}
            onClearSessions={onClearSessions}
          />
        )}
        {activeView === 'settings' && <SettingsPanel settings={settings} onSettingsChange={onSettingsChange} />}
      </section>
    </aside>
  );
}

function ActivityPanel({ activity }: { activity: AgentActivityStep[] }) {
  if (activity.length === 0) {
    return <p className="text-muted text-sm">요청을 보내면 에이전트 활동이 표시됩니다.</p>;
  }

  return (
    <div className="h-full overflow-y-auto pr-1">
      <h3 className="text-muted mb-3 text-xs font-semibold uppercase">에이전트 활동</h3>
      <div className="space-y-3">
        {activity.map((step, index) => (
          <div key={`${step.label}-${index}`} className="flex gap-3">
            <div
              className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
                step.status === 'error' ? 'bg-red-100 text-red-700' : 'bg-ink text-white'
              }`}
            >
              {index + 1}
            </div>
            <div>
              <div className="text-sm font-medium">{localizeToolNames(step.label)}</div>
              <div className="text-muted text-xs leading-5">{localizeToolNames(step.description)}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ToolsPanel({ tools, error }: { tools: ToolInfo[]; error: string | null }) {
  if (error) {
    return (
      <p className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
        {error}
      </p>
    );
  }

  if (tools.length === 0) {
    return <p className="text-muted text-sm">등록된 도구가 없습니다.</p>;
  }

  return (
    <div className="h-full overflow-y-auto pr-1">
      <h3 className="text-muted mb-3 text-xs font-semibold uppercase">등록된 도구</h3>
      <div className="space-y-2">
        {tools.map((tool) => (
          <div key={tool.name} className="card-subtle p-2.5">
            <div className="mb-1 flex items-center justify-between gap-2">
              <span className="truncate text-sm font-medium">{getToolDisplayName(tool)}</span>
              <ToolStatus status={tool.status} />
            </div>
            <p className="clamp-2 text-muted text-xs leading-5">{getToolDescription(tool)}</p>
            <dl className="mt-1.5 space-y-1 text-xs">
              <InfoLine label="상태" value={toolStatusText(tool.status)} />
              <InfoLine label="실행 가능 여부" value={tool.status === 'active' ? '실행 가능' : '확인 필요'} />
              <InfoLine label="상세" value={toolDetail(tool)} />
            </dl>
          </div>
        ))}
      </div>
    </div>
  );
}

function HistoryPanel({
  sessions,
  currentSessionId,
  onRestoreSession,
  onDeleteSession,
  onClearSessions,
}: {
  sessions: ChatSession[];
  currentSessionId: string;
  onRestoreSession: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => void;
  onClearSessions: () => void;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="mb-3 flex shrink-0 items-center justify-between gap-2">
        <h3 className="text-muted text-xs font-semibold uppercase">대화 기록</h3>
        <button
          className="text-muted rounded p-1 hover:bg-slate-100 hover:text-red-600 dark:hover:bg-slate-800"
          onClick={onClearSessions}
          title="전체 삭제"
          aria-label="전체 대화 기록 삭제"
        >
          <Trash2 size={15} aria-hidden="true" />
        </button>
      </div>
      {sessions.length === 0 ? (
        <p className="text-muted text-sm">저장된 대화가 없습니다.</p>
      ) : (
        <div className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
          {sessions.map((session) => (
            <button
              key={session.id}
              className={`w-full rounded border p-3 text-left ${
                session.id === currentSessionId
                  ? 'border-slate-900 bg-slate-50 dark:border-slate-100 dark:bg-slate-800'
                  : 'border-slate-200 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800'
              }`}
              onClick={() => onRestoreSession(session.id)}
            >
              <div className="flex items-start gap-2">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{session.title}</div>
                  <div className="text-faint mt-1 truncate text-xs">{sessionPreview(session)}</div>
                  <div className="text-muted mt-1 text-xs">{new Date(session.updatedAt).toLocaleString()}</div>
                </div>
                <span
                  role="button"
                  tabIndex={0}
                  className="text-muted shrink-0 rounded p-1 hover:bg-slate-100 hover:text-red-600 dark:hover:bg-slate-700"
                  title="삭제"
                  aria-label="대화 삭제"
                  onClick={(event) => {
                    event.stopPropagation();
                    onDeleteSession(session.id);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      event.stopPropagation();
                      onDeleteSession(session.id);
                    }
                  }}
                >
                  <X size={14} aria-hidden="true" />
                </span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function SettingsPanel({
  settings,
  onSettingsChange,
}: {
  settings: DashboardSettings;
  onSettingsChange: (settings: DashboardSettings) => void;
}) {
  return (
    <div className="h-full overflow-y-auto pr-1">
      <h3 className="text-muted mb-3 text-xs font-semibold uppercase">시스템 상태</h3>
      <div className="card-subtle space-y-2 p-3 text-sm">
        <InfoLine label="멀티 에이전트" value="활성화" />
        <InfoLine label="모델 라우팅" value="활성화" />
      </div>

      <div className="mt-4">
        <span className="text-muted mb-2 block text-xs font-semibold uppercase">화면 테마</span>
        <div className="grid grid-cols-2 rounded border border-slate-300 p-1 dark:border-slate-700">
          {(['light', 'dark'] as const).map((theme) => (
            <button
              key={theme}
              className={`h-8 rounded text-sm ${settings.theme === theme ? 'segmented-active' : 'segmented-idle'}`}
              onClick={() => onSettingsChange({ ...settings, theme })}
            >
              {theme === 'light' ? '라이트' : '다크'}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function ToolStatus({ status }: { status: ToolInfo['status'] }) {
  if (status === 'active') {
    return <CheckCircle2 size={16} className="text-emerald-600" aria-label="활성" />;
  }
  if (status === 'error') {
    return <AlertCircle size={16} className="text-red-600" aria-label="오류" />;
  }
  return <Circle size={16} className="text-slate-400" aria-label="준비 중" />;
}

function InfoLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-muted shrink-0">{label}</dt>
      <dd className="break-all text-right font-medium">{value}</dd>
    </div>
  );
}

function toolStatusText(status: ToolInfo['status']): string {
  if (status === 'active') {
    return '활성화';
  }
  if (status === 'error') {
    return '오류';
  }
  return '준비 중';
}

function toolDetail(tool: ToolInfo): string {
  if (tool.detail.includes('found on PATH')) {
    return '실행 파일이 PATH에 등록되어 있습니다.';
  }
  if (tool.detail.includes('not found on PATH')) {
    return '실행 파일을 PATH에서 찾을 수 없습니다.';
  }
  if (tool.detail.includes('registered in tool registry')) {
    return '백엔드 tool registry에 등록되어 있습니다.';
  }
  return tool.detail;
}

function sessionPreview(session: ChatSession): string {
  const message = session.messages.find((item) => item.role === 'user') ?? session.messages[0];
  return message?.content ?? '아직 메시지가 없습니다.';
}
