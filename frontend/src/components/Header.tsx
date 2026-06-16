import { Bot } from "lucide-react";

import type { ApiStatus } from "../api/client";
import type { DashboardSettings } from "../types/chat";
import { StatusPill } from "./StatusPill";

type HeaderProps = {
  apiStatus: ApiStatus;
  settings: DashboardSettings;
  toolsLoaded: number;
};

export function Header({ apiStatus, settings, toolsLoaded }: HeaderProps) {
  return (
    <header className="surface flex h-16 shrink-0 items-center justify-between border-b px-6">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded bg-ink text-white">
          <Bot size={22} aria-hidden="true" />
        </div>
        <div>
          <h1 className="text-lg font-semibold">MAOS Dashboard</h1>
          <p className="text-muted text-sm">AI Runtime Architecture</p>
        </div>
      </div>
      <StatusPill
        status={apiStatus}
        settings={settings}
        toolsLoaded={toolsLoaded}
      />
    </header>
  );
}
