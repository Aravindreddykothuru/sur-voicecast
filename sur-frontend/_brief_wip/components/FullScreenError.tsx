/**
 * The whole app renders this instead of any screen when /api/capabilities
 * fails. No fallback language/emotion list, no cached defaults -- an app
 * that can't confirm what the backend supports must not guess. See
 * sur-backend/CONTRACTS.md #2 and #3.
 */
export function FullScreenError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex h-full w-full items-center justify-center" style={{ background: "var(--bg-app)" }}>
      <div className="panel flex max-w-md flex-col items-center gap-3 p-8 text-center">
        <div
          className="flex h-10 w-10 items-center justify-center rounded-full"
          style={{ background: "color-mix(in srgb, var(--err) 12%, transparent)", color: "var(--err)" }}
        >
          !
        </div>
        <p className="text-section-title">Can't reach the backend</p>
        <p className="text-body" style={{ color: "var(--text-secondary)" }} role="alert">
          {message}
        </p>
        <p className="text-meta">
          This app only offers languages and options the backend actually supports, so it can't render
          anything until it can confirm what those are.
        </p>
        <button className="btn-primary mt-2" onClick={onRetry}>
          Try again
        </button>
      </div>
    </div>
  );
}
