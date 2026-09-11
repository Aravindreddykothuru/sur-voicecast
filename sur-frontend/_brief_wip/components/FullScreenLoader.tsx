export function FullScreenLoader({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex h-full w-full items-center justify-center" style={{ background: "var(--bg-app)" }}>
      <div className="flex flex-col items-center gap-3">
        <div
          className="h-8 w-8 animate-spin rounded-full border-2"
          style={{ borderColor: "var(--border-strong)", borderTopColor: "var(--accent)" }}
        />
        <p className="text-meta">{label}</p>
      </div>
    </div>
  );
}
