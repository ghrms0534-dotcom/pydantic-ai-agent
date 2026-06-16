import { BrainCircuit, History, Settings, Wrench } from 'lucide-react';

import type { ChatMessage, DashboardSettings } from '../types/chat';

export const starterMessages: ChatMessage[] = [
  {
    id: 'welcome',
    role: 'agent',
    content: '대시보드 준비 완료. 쿠버네티스, GitHub, 코드 작업 등을 물어보세요.',
  },
];

export const navigationItems = [
  { id: 'trace', label: '에이전트 활동', icon: BrainCircuit },
  { id: 'tools', label: '도구', icon: Wrench },
  { id: 'history', label: '대화 기록', icon: History },
  { id: 'settings', label: '설정', icon: Settings },
];

export const defaultSettings: DashboardSettings = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000',
  agentName: '통합 에이전트',
  modelName: 'qwen2.5:3b',
  theme: 'light',
};
