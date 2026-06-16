import { useEffect, useRef, useState } from 'react';
import { Activity, CheckCircle2, Circle, Copy, Loader2, Send } from 'lucide-react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';

import type { ChatMessage, ToolInfo } from '../types/chat';

type ChatConsoleProps = {
  messages: ChatMessage[];
  input: string;
  loading: boolean;
  error: string | null;
  tools: ToolInfo[];
  onInputChange: (value: string) => void;
  onSend: () => void;
};

const markdownComponents: Components = {
  h1: ({ children }) => <h1 className="mb-1.5 mt-1 text-lg font-semibold">{children}</h1>,
  h2: ({ children }) => <h2 className="mb-1.5 mt-2 text-base font-semibold">{children}</h2>,
  h3: ({ children }) => <h3 className="mb-1.5 mt-2 text-sm font-semibold">{children}</h3>,
  p: ({ children }) => <p className="mb-1.5 last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="mb-1.5 list-disc space-y-0.5 pl-5 last:mb-0">{children}</ul>,
  ol: ({ children }) => <ol className="mb-1.5 list-decimal space-y-0.5 pl-5 last:mb-0">{children}</ol>,
  li: ({ children }) => <li className="pl-1">{children}</li>,
  code: ({ className, children, ...props }) => {
    const code = String(children).replace(/\n$/, '');
    const match = /language-(\w+)/.exec(className ?? '');

    if (match || code.includes('\n')) {
      return <CodeBlock code={code} language={match?.[1] ?? 'code'} />;
    }

    return (
      <code
        className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[0.85em] text-slate-900 dark:bg-slate-800 dark:text-slate-100"
        {...props}
      >
        {children}
      </code>
    );
  },
};

export function ChatConsole({ messages, input, loading, error, tools, onInputChange, onSend }: ChatConsoleProps) {
  const [orchestratorOpen, setOrchestratorOpen] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' });
  }, [messages, loading]);

  return (
    <main className="workspace flex min-h-0 min-w-0 flex-col">
      <section className="surface shrink-0 border-b px-5 py-3">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold">에이전트 콘솔</h2>
            <p className="text-muted text-sm">질문을 입력하면 통합 에이전트가 필요한 기능을 선택해 응답합니다.</p>
          </div>
          <div className="relative">
            <button
              className="text-muted flex h-9 items-center gap-2 rounded border border-transparent px-3 text-sm hover:bg-slate-100 dark:hover:bg-slate-800"
              onClick={() => setOrchestratorOpen((current) => !current)}
            >
              <Activity size={17} aria-hidden="true" />
              통합 에이전트
            </button>
            {orchestratorOpen && (
              <div className="card absolute right-0 top-11 z-20 w-72 p-4">
                <div className="mb-3 text-sm font-semibold">에이전트 연결 상태</div>
                <StatusLine label="Chat Agent" active />
                <StatusLine label="Git Agent" active={isToolActive(tools, 'git_status')} />
                <StatusLine label="Kubernetes Agent" active={isToolActive(tools, 'k8s')} />
                <StatusLine label="GitHub Agent" active={isToolActive(tools, 'github')} />
                <StatusLine label="Docker Agent" active={false} />
              </div>
            )}
          </div>
        </div>
      </section>

      <section className="min-h-0 flex-1 overflow-y-auto px-5 py-3">
        <div className="flex w-full flex-col gap-2.5">
          {messages.map((message) => {
            const isUser = message.role === 'user';
            return (
              <div key={message.id} className={`flex w-full ${isUser ? 'justify-end' : 'justify-start'}`}>
                <article
                  className={`card min-w-[250px] break-words px-3 py-2 ${
                    isUser ? 'max-w-[78%] border-slate-300' : 'max-w-[82%]'
                  }`}
                >
                  <div className="text-muted mb-0.5 text-[11px] font-semibold uppercase">
                    {isUser ? '사용자' : '에이전트'}
                  </div>
                  {isUser ? (
                    <p className="whitespace-pre-wrap break-words text-sm leading-5">{message.content}</p>
                  ) : (
                    <div className="markdown-message break-words text-sm leading-5">
                      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                        {message.content}
                      </ReactMarkdown>
                    </div>
                  )}
                </article>
              </div>
            );
          })}

          {loading && (
            <div className="flex w-full justify-start">
              <div className="card text-muted flex items-center gap-2 px-3 py-2 text-sm">
                <Loader2 className="animate-spin" size={17} aria-hidden="true" />
                에이전트가 응답을 준비 중입니다.
              </div>
            </div>
          )}

          {error && (
            <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
              {error}
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </section>

      <section className="surface shrink-0 border-t p-4">
        <div className="flex w-full gap-3">
          <input
            className="field h-11 flex-1 rounded border px-4 text-sm"
            value={input}
            onChange={(event) => onInputChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                onSend();
              }
            }}
            placeholder="쿠버네티스, GitHub, 코드 작업 등을 물어보세요."
          />
          <button
            className="primary-btn flex h-11 items-center gap-2 rounded px-5 text-sm font-medium"
            onClick={onSend}
            disabled={loading || !input.trim()}
          >
            {loading ? <Loader2 className="animate-spin" size={17} /> : <Send size={17} />}
            전송
          </button>
        </div>
      </section>
    </main>
  );
}

function CodeBlock({ code, language }: { code: string; language: string }) {
  const [copied, setCopied] = useState(false);
  const label = language ? language[0].toUpperCase() + language.slice(1) : 'Code';

  async function handleCopy() {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  }

  return (
    <div className="my-2.5 overflow-hidden rounded-lg border border-slate-700 bg-slate-950 text-slate-100">
      <div className="flex h-9 items-center justify-between border-b border-slate-800 bg-slate-900 px-4 text-xs">
        <span className="font-medium text-slate-300">{label}</span>
        <button
          className="flex items-center gap-1 rounded px-2 py-1 text-slate-300 hover:bg-slate-800 hover:text-white"
          onClick={() => void handleCopy()}
        >
          <Copy size={13} aria-hidden="true" />
          {copied ? '복사됨' : '복사'}
        </button>
      </div>
      <pre className="overflow-x-auto p-3 text-[13px] leading-5">
        <code className="font-mono">{code}</code>
      </pre>
    </div>
  );
}

function StatusLine({ label, active }: { label: string; active: boolean }) {
  return (
    <div className="mb-2 grid grid-cols-[minmax(0,1fr)_82px] items-center gap-3 last:mb-0">
      <span className="truncate text-xs font-medium">{label}</span>
      <span className={`flex items-center justify-end gap-1 text-xs ${active ? 'text-emerald-600' : 'text-slate-400'}`}>
        {active ? <CheckCircle2 size={14} /> : <Circle size={14} />}
        {active ? '사용 가능' : '준비 중'}
      </span>
    </div>
  );
}

function isToolActive(tools: ToolInfo[], keyword: string): boolean {
  return tools.some((tool) => tool.name.includes(keyword) && tool.status === 'active');
}
