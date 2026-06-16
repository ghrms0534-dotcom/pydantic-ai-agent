import { useState } from 'react';
import { Clock3, Play } from 'lucide-react';

import type { ApiStatus } from '../api/client';
import type { DashboardSettings } from '../types/chat';

type StatusPillProps = {
  status: ApiStatus;
  settings: DashboardSettings;
  toolsLoaded: number;
};

export function StatusPill({ status, settings, toolsLoaded }: StatusPillProps) {
  const [open, setOpen] = useState(false);
  const label = status === 'checking' ? 'AI 연결 확인 중' : status === 'online' ? 'AI 연결 정상' : 'AI 연결 오프라인';
  const server = status === 'checking' ? '확인 중' : status === 'online' ? '정상' : '오프라인';
  const className =
    status === 'online'
      ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-300'
      : status === 'offline'
        ? 'border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300'
        : 'border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300';

  return (
    <div className="relative">
      <button
        className={`flex h-9 items-center gap-2 rounded border px-3 text-sm font-medium ${className}`}
        onClick={() => setOpen((current) => !current)}
      >
        {status === 'checking' ? <Clock3 size={16} aria-hidden="true" /> : <Play size={16} aria-hidden="true" />}
        {label}
      </button>
      {open && (
        <div className="card absolute right-0 top-11 z-20 w-72 p-4">
          <div className="mb-3 text-sm font-semibold">시스템 상태</div>
          <StatusRow label="서버" value={server} />
          <StatusRow label="실행 모드" value={settings.agentName} />
          <StatusRow label="AI 모델" value={settings.modelName} />
          <StatusRow label="사용 가능 도구" value={`${toolsLoaded}`} />
        </div>
      )}
    </div>
  );
}

function StatusRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="mb-2 flex items-start justify-between gap-3 last:mb-0">
      <span className="text-muted shrink-0 text-xs">{label}</span>
      <span className="break-all text-right text-xs font-medium">{value}</span>
    </div>
  );
}
