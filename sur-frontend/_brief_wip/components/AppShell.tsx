import type { ReactNode } from "react";
import { Sidebar, type NavKey } from "./Sidebar";
import { TopBar } from "./TopBar";

interface AppShellProps {
  active: NavKey | null;
  pageTitle: string;
  userEmail: string;
  onNavigate: (key: NavKey) => void;
  onNewDubbing: () => void;
  children: ReactNode;
}

export function AppShell({ active, pageTitle, userEmail, onNavigate, onNewDubbing, children }: AppShellProps) {
  return (
    <div className="flex h-full w-full" style={{ background: "var(--bg-app)" }}>
      <Sidebar active={active} onNavigate={onNavigate} onNewDubbing={onNewDubbing} />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar title={pageTitle} userEmail={userEmail} />
        <main className="flex-1 overflow-y-auto p-6">
          <div className="mx-auto flex flex-col gap-4" style={{ maxWidth: "var(--content-max-w)" }}>
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
