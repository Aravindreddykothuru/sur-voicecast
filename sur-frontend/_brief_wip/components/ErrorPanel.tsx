/**
 * Panel (d): Errors. Permanent ("This run cannot succeed") vs transient
 * ("Temporary failure") tone, the real backend message, the stage it failed
 * on, and Retry only when it isn't permanent. Retry re-invokes
 * POST /process with the project's own existing options -- there is no
 * per-stage resume endpoint, so this restarts the pipeline from
 * extract_audio rather than from the failed stage; that's the real
 * capability that exists (app/api/routes_projects.py start_processing has
 * no stage-resume path).
 */
import type { ProjectError } from "../lib/types";

export function ErrorPanel({
  error,
  onRetry,
  retrying,
}: {
  error: ProjectError;
  onRetry: () => void;
  retrying: boolean;
}) {
  const isPermanent = error.kind === "permanent";
  return (
    <div
      className="panel flex flex-col gap-2 p-5"
      style={{ borderColor: isPermanent ? "var(--err)" : "var(--warn)" }}
      role="alert"
    >
      <div className="flex items-center gap-2">
        <span
          className="rounded-full px-2 py-0.5 text-meta font-medium"
          style={{
            background: isPermanent ? "color-mix(in srgb, var(--err) 14%, transparent)" : "color-mix(in srgb, var(--warn) 14%, transparent)",
            color: isPermanent ? "var(--err)" : "var(--warn)",
          }}
        >
          {isPermanent ? "This run cannot succeed" : "Temporary failure"}
        </span>
        {error.stage && <span className="text-meta">stage: {error.stage}</span>}
      </div>
      <p className="text-body">{error.message}</p>
      {!isPermanent && (
        <button className="btn-secondary self-start" disabled={retrying} onClick={onRetry}>
          {retrying ? "Retrying…" : "Retry"}
        </button>
      )}
    </div>
  );
}
