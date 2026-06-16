import type { ReactNode } from 'react';
import { AlertCircle, CheckCircle2, Circle } from 'lucide-react';

import type { DashboardSettings, ToolInfo } from '../types/chat';
import { getAgentCapabilities } from '../utils/toolDisplay';

type RightPanelProps = {
  settings: DashboardSettings;
  tools: ToolInfo[];
  recentAgent: string;
};

export function RightPanel({ tools, recentAgent }: RightPanelProps) {
  const capabilities = getAgentCapabilities(tools);

  return (
    <aside className="surface min-h-0 overflow-y-auto border-l p-4">
      <Panel title="런타임 정보">
        <InfoRow label="기본 모델" value="qwen2.5:3b" />
        <InfoRow label="모델 라우팅" value="활성화" />
        <InfoRow label="연결 상태" value="정상 연결됨" />
      </Panel>

      <Panel title="에이전트 기능">
        <div className="space-y-2">
          {capabilities.map((capability) => (
            <div key={capability.id} className="card-subtle flex min-h-[48px] items-center justify-between gap-3 px-3 py-2">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">{capability.name}</div>
                <div className="text-muted mt-0.5 text-xs leading-4">{capability.description}</div>
              </div>
              <span className="flex shrink-0 items-center gap-1 whitespace-nowrap text-xs">
                <CapabilityStatus status={capability.status} />
                {capability.status === 'active' ? '사용 가능' : '준비 중'}
              </span>
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="실행 정보">
        <InfoRow label="최근 실행" value={formatRecentAgent(recentAgent)} />
        <InfoRow label="총 요청" value="14회" />
        <InfoRow label="평균 응답" value="1.3초" />
        <InfoRow label="사용 시간" value="18분" />
      </Panel>
    </aside>
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mb-4">
      <h3 className="text-muted mb-3 text-sm font-semibold uppercase">{title}</h3>
      <div className="card p-3">{children}</div>
    </section>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="mb-2.5 flex items-center justify-between gap-3 last:mb-0">
      <span className="text-muted min-w-0 text-left text-sm">{label}</span>
      <span className="min-w-[88px] truncate text-right text-sm font-medium">{value}</span>
    </div>
  );
}

function CapabilityStatus({ status }: { status: ToolInfo['status'] }) {
  if (status === 'active') {
    return <CheckCircle2 size={16} className="shrink-0 text-emerald-600" aria-label="활성" />;
  }
  if (status === 'error') {
    return <AlertCircle size={16} className="shrink-0 text-red-600" aria-label="오류" />;
  }
  return <Circle size={16} className="shrink-0 text-slate-400" aria-label="준비 중" />;
}

function formatRecentAgent(agent: string): string {
  if (agent === 'DevOps Agent') {
    return 'Kubernetes Agent';
  }
  return agent;
}
