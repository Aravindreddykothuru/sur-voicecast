interface TopBarProps {
  title: string;
  userEmail: string;
}

export function TopBar({ title, userEmail }: TopBarProps) {
  const initial = userEmail.trim().charAt(0).toUpperCase() || "?";

  return (
    <header
      className="flex items-center justify-between px-6 py-4"
      style={{ borderBottom: "1px solid var(--border)", background: "var(--bg-panel)" }}
    >
      <h1 className="text-page-title">{title}</h1>
      <div className="flex items-center gap-4">
        <button className="text-label" style={{ color: "var(--text-secondary)" }}>
          Help
        </button>
        <div
          className="flex h-8 w-8 items-center justify-center rounded-full text-label font-medium"
          style={{ background: "var(--bg-hover)", color: "var(--text-primary)" }}
          title={userEmail}
        >
          {initial}
        </div>
      </div>
    </header>
  );
}
