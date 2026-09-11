/**
 * Screen 4: Runtime panel (device, model load state, limits).
 *
 * "Model load state" is shown as configured PROVIDER MODE (mock/real) --
 * that's all /api/capabilities actually reports. Whether a real provider's
 * weights are currently loaded in a worker process is not exposed by any
 * endpoint today: sur-backend's fail-loud startup check
 * (app/startup_checks.py) runs once when a worker boots and either lets it
 * start or kills it (WorkerShutdown) -- it doesn't persist a queryable
 * result anywhere. Reporting "loaded" here would be a guess this app isn't
 * allowed to make. A live per-provider load-state endpoint (e.g. a Redis
 * key each worker sets after its own self-check) is a real backend gap.
 */
import { useReadyCapabilities } from "../lib/capabilities";

const PROVIDER_LABELS: Record<string, string> = {
  asr: "Speech recognition",
  diarization: "Diarization",
  translation: "Translation",
  emotion: "Emotion detection",
  tts: "Voice synthesis",
};

export function RuntimeScreen() {
  const caps = useReadyCapabilities();

  return (
    <div className="flex flex-col gap-4">
      <div className="panel flex flex-col gap-3 p-5">
        <h3 className="text-section-title">Device</h3>
        <div className="flex items-center gap-2">
          <span
            className="rounded-full px-3 py-1 text-label font-medium"
            style={{
              background: caps.device === "cpu" ? "color-mix(in srgb, var(--warn) 14%, transparent)" : "color-mix(in srgb, var(--ok) 14%, transparent)",
              color: caps.device === "cpu" ? "var(--warn)" : "var(--ok)",
            }}
          >
            {caps.device.toUpperCase()}
          </span>
          <span className="text-meta">
            {caps.device === "cpu" ? "~2 min per sentence on CPU" : "GPU-accelerated"}
          </span>
        </div>
      </div>

      <div className="panel flex flex-col gap-3 p-5">
        <h3 className="text-section-title">Providers</h3>
        <p className="text-meta">
          Configured mode per stage. This is not a live load check -- see this file's header comment for why.
        </p>
        <div className="flex flex-col gap-2">
          {Object.entries(caps.providers).map(([stage, mode]) => (
            <div key={stage} className="flex items-center justify-between">
              <span className="text-label">{PROVIDER_LABELS[stage] ?? stage}</span>
              <span
                className="rounded-full px-2 py-0.5 text-meta font-medium"
                style={{
                  background: mode === "real" ? "color-mix(in srgb, var(--ok) 14%, transparent)" : "var(--bg-hover)",
                  color: mode === "real" ? "var(--ok)" : "var(--text-secondary)",
                }}
              >
                {mode}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="panel flex flex-col gap-3 p-5">
        <h3 className="text-section-title">Limits</h3>
        <div className="flex flex-col gap-1 text-body">
          <span>Max upload size: {caps.max_upload_mb}MB</span>
          <span>Accepted formats: {caps.accepted_formats.join(", ")}</span>
          <span>Emotion confidence floor: {Math.round(caps.emotion_confidence_floor * 100)}%</span>
        </div>
      </div>
    </div>
  );
}
