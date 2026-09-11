/**
 * Replaces the reference product's "Free Plan / Upgrade" sidebar slot with
 * honest content: this app has no plans or billing, so that slot shows the
 * one thing that's actually true and actually useful here -- what hardware
 * the pipeline is running on, since that's what determines whether a dub
 * takes seconds or tens of minutes.
 */
import { useReadyCapabilities } from "../lib/capabilities";

export function RuntimeMiniCard() {
  const caps = useReadyCapabilities();
  const isCpu = caps.device === "cpu";

  return (
    <div className="panel flex flex-col gap-1.5 p-3" style={{ background: "var(--bg-panel-muted)" }}>
      <div className="flex items-center justify-between">
        <span className="text-label">Runtime</span>
        <span
          className="rounded-full px-2 py-0.5 text-meta font-medium"
          style={{
            background: isCpu ? "color-mix(in srgb, var(--warn) 14%, transparent)" : "color-mix(in srgb, var(--ok) 14%, transparent)",
            color: isCpu ? "var(--warn)" : "var(--ok)",
          }}
        >
          {caps.device.toUpperCase()}
        </span>
      </div>
      <p className="text-meta">{isCpu ? "~2 min per sentence on CPU" : "GPU-accelerated"}</p>
    </div>
  );
}
