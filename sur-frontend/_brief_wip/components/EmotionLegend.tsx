/**
 * Renders ONLY caps.emotions plus "uncertain" -- never a hardcoded six-way
 * emotion set. A model swap that predicts three labels instead of six
 * shrinks this legend automatically.
 */
import { useReadyCapabilities } from "../lib/capabilities";
import { emotionColor, UNCERTAIN_COLOR } from "../lib/theme";

export function EmotionLegend() {
  const caps = useReadyCapabilities();
  return (
    <div className="flex flex-wrap items-center gap-3">
      {caps.emotions.map((e) => (
        <span key={e.label} className="flex items-center gap-1.5 text-meta">
          <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: emotionColor(e.index) }} />
          {e.label}
        </span>
      ))}
      <span className="flex items-center gap-1.5 text-meta">
        <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: UNCERTAIN_COLOR }} />
        uncertain
      </span>
    </div>
  );
}
