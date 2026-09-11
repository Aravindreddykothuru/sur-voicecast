import { RuntimeMiniCard } from "./RuntimeMiniCard";

export type NavKey = "projects" | "runtime" | "settings";

interface SidebarProps {
  active: NavKey | null;
  onNavigate: (key: NavKey) => void;
  onNewDubbing: () => void;
}

const NAV_ITEMS: { key: NavKey; label: string }[] = [
  { key: "projects", label: "Projects" },
  { key: "runtime", label: "Runtime" },
  { key: "settings", label: "Settings" },
];

export function Sidebar({ active, onNavigate, onNewDubbing }: SidebarProps) {
  return (
    <aside
      className="flex h-full flex-col justify-between p-4"
      style={{ width: "var(--sidebar-w)", borderRight: "1px solid var(--border)", background: "var(--bg-panel)" }}
    >
      <div className="flex flex-col gap-6">
        <div className="flex items-center gap-2 px-2 py-1">
          <div
            className="flex h-7 w-7 items-center justify-center rounded-md text-sm font-semibold"
            style={{ background: "var(--accent)", color: "var(--text-on-accent)" }}
          >
            S
          </div>
          <span className="text-section-title">Sur</span>
        </div>

        <nav className="flex flex-col gap-1">
          <button
            className="btn-primary mb-2 w-full text-left"
            style={{ textAlign: "center" }}
            onClick={onNewDubbing}
          >
            + New Dubbing
          </button>

          {NAV_ITEMS.map((item) => (
            <button
              key={item.key}
              onClick={() => onNavigate(item.key)}
              className="rounded-md px-3 py-2 text-left text-label transition-colors"
              style={{
                background: active === item.key ? "var(--bg-hover)" : "transparent",
                color: active === item.key ? "var(--text-primary)" : "var(--text-secondary)",
              }}
            >
              {item.label}
            </button>
          ))}
        </nav>
      </div>

      <RuntimeMiniCard />
    </aside>
  );
}
