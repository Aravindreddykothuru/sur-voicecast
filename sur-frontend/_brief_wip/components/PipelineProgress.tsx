/**
 * Panel (a): Progress. All 7 stages, never a bare spinner -- each row shows
 * a state dot, the stage name, a progress bar, and item counts/ETA when the
 * backend has reported them ("4/17 · ~12m"). Stage keys and order come from
 * PIPELINE_STAGE_ORDER (app/pipeline/tasks.py's real chain), not a
 * hand-picked subset.
 */
import { PIPELINE_STAGE_LABELS } from "../lib/types";
import type { StageState } from "../lib/useProjectEvents";

function StateDot({ stage }: { stage: StageState }) {
  const color = stage.done ? "var(--ok)" : stage.active ? "var(--warn)" : "var(--border-strong)";
  return <span className="inline-block h-2 w-2 rounded-full" style={{ background: color }} />;
}

export function PipelineProgress({ stages }: { stages: StageState[] }) {
  return (
    <div className="panel flex flex-col gap-3 p-5">
      <h3 className="text-section-title">Progress</h3>
      <div className="flex flex-col gap-2">
        {stages.map((stage) => {
          const pct = Math.round(stage.progress * 100);
          const countLabel = stage.completed != null && stage.total != null ? `${stage.completed}/${stage.total}` : null;
          return (
            <div key={stage.key} className="flex items-center gap-3">
              <StateDot stage={stage} />
              <span className="w-40 shrink-0 text-label">{PIPELINE_STAGE_LABELS[stage.key]}</span>
              <div className="h-1.5 flex-1 overflow-hidden rounded-full" style={{ background: "var(--border)" }}>
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${stage.done ? 100 : pct}%`,
                    background: stage.done ? "var(--ok)" : "var(--accent)",
                  }}
                />
              </div>
              <span className="w-28 shrink-0 text-right font-mono text-meta">
                {stage.done
                  ? "Done"
                  : stage.active
                    ? [countLabel, stage.eta ? `~${stage.eta}` : null].filter(Boolean).join(" · ") || `${pct}%`
                    : "Waiting"}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
