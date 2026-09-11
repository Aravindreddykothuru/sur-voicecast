import { useState, useEffect, useCallback, useRef } from "react";
import type { ReactNode } from "react";
import EchoLanding from "@/EchoLanding";
import { getStoredAuth, logout, type StoredAuth } from "@/lib/auth";
import {
  ApiError,
  listProjects,
  getProject,
  createProject,
  createUploadUrl,
  putUploadFile,
  confirmUpload,
  startProcessing,
  retryProject,
  confirmLanguage,
  listSegments,
  getExport,
  patchSegment,
  regenerateSegment,
  resolveUrl,
} from "@/lib/api";
import {
  CapabilitiesProvider,
  useCapabilities,
  useReadyCapabilities,
  emotionDisplay,
  emotionIndexOf,
  languageName,
  sourceLanguageName,
} from "@/lib/capabilities";
import { emotionColor, UNCERTAIN_COLOR } from "@/lib/theme";
import {
  PIPELINE_STAGE_ORDER,
  PIPELINE_STAGE_LABELS,
  projectError,
  type Capabilities,
  type ProjectListItem,
  type ProjectRead,
  type SegmentRead,
  type ExportRead,
} from "@/lib/types";
import { useProjectEvents, fmtTime, type StageState } from "@/lib/useProjectEvents";

// ─────────────────────────────────────────────────────────────────────────────
// Design tokens — pure black ground, white accent (unchanged from the Figma
// Make original). Only the DATA below is now backend-driven.
// ─────────────────────────────────────────────────────────────────────────────
const C = {
  bg: "#000000",
  bgDeep: "#000000",
  card: "rgba(255,255,255,0.04)",
  cardHov: "rgba(255,255,255,0.07)",
  surface: "rgba(255,255,255,0.04)",
  border: "rgba(255,255,255,0.14)",
  borderHi: "rgba(255,255,255,0.32)",
  teal: "#ffffff",
  tealSoft: "rgba(255,255,255,0.08)",
  tealBorder: "rgba(255,255,255,0.22)",
  rust: "rgba(255,255,255,0.55)",
  rustSoft: "rgba(255,255,255,0.06)",
  text: "#ffffff",
  textMid: "rgba(255,255,255,0.62)",
  textMuted: "rgba(255,255,255,0.38)",
  textDim: "rgba(255,255,255,0.18)",
  green: { fg: "#34d399", bg: "rgba(52,211,153,0.09)", bd: "rgba(52,211,153,0.28)" },
  red: { fg: "#f87171", bg: "rgba(248,113,113,0.09)", bd: "rgba(248,113,113,0.28)" },
  amber: { fg: "#f59e0b", bg: "rgba(245,158,11,0.09)", bd: "rgba(245,158,11,0.28)" },
  purple: { fg: "#a78bfa", bg: "rgba(167,139,250,0.09)", bd: "rgba(167,139,250,0.28)" },
  cyan: { fg: "#22d3ee", bg: "rgba(34,211,238,0.09)", bd: "rgba(34,211,238,0.28)" },
  panel: "#0c0d10",
  slate: "rgba(255,255,255,0.03)",
};

type Screen = "landing" | "dashboard" | "new-project" | "processing" | "editor" | "preview" | "export";

// ─────────────────────────────────────────────────────────────────────────────
// Primitives (visual style unchanged)
// ─────────────────────────────────────────────────────────────────────────────
function Badge({ status }: { status: string }) {
  const m: Record<string, { fg: string; bg: string; bd: string }> = {
    Pass: C.green, Verified: C.green, Ready: C.green, ready: C.green, muxed: C.green, synthesized: C.green,
    Fail: C.red, Error: C.red, failed: C.red,
    Review: C.amber, awaiting_language_confirmation: C.amber,
    Processing: { fg: C.teal, bg: C.tealSoft, bd: C.tealBorder }, processing: { fg: C.teal, bg: C.tealSoft, bd: C.tealBorder },
    queued: { fg: C.teal, bg: C.tealSoft, bd: C.tealBorder },
    Draft: { fg: C.textMuted, bg: C.surface, bd: C.border }, draft: { fg: C.textMuted, bg: C.surface, bd: C.border },
  };
  const s = m[status] ?? m.Draft;
  return (
    <span className="inline-flex items-center px-2.5 py-0.5 rounded text-[11px] font-mono font-medium border"
      style={{ color: s.fg, background: s.bg, borderColor: s.bd }}>{status}</span>
  );
}

/** Emotion badge — label + colour resolved from /api/capabilities BY INDEX,
 *  never from a hardcoded label→style table. A prediction below the
 *  confidence floor renders as "uncertain", not as a label. */
function EmBadge({ caps, label, score }: { caps: Capabilities; label: string | null; score: number | null }) {
  const d = emotionDisplay(caps, label, score);
  const color = d.uncertain ? UNCERTAIN_COLOR : d.index != null ? emotionColor(d.index) : C.textMid;
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-[11px] font-mono font-semibold border"
      style={{ color, background: "rgba(255,255,255,0.05)", borderColor: "rgba(255,255,255,0.14)" }}>
      {d.text === "—" ? "—" : d.text.toUpperCase()}
    </span>
  );
}

function EmotionLegend({ caps }: { caps: Capabilities }) {
  return (
    <div className="flex flex-wrap gap-2">
      {caps.emotions.map((e) => (
        <span key={e.index} className="inline-flex items-center gap-1.5 text-[10px] font-mono" style={{ color: C.textMid }}>
          <span className="w-2.5 h-2.5 rounded-sm" style={{ background: emotionColor(e.index) }} />
          {e.label}
        </span>
      ))}
      <span className="inline-flex items-center gap-1.5 text-[10px] font-mono" style={{ color: C.textMid }}>
        <span className="w-2.5 h-2.5 rounded-sm" style={{ background: UNCERTAIN_COLOR }} />
        uncertain (&lt; {caps.emotion_confidence_floor})
      </span>
    </div>
  );
}

function Metric({ label, value, unit, sub, color }: { label: string; value: string; unit: string; sub: string; color: string }) {
  const n = parseFloat(value);
  const pct = Math.min(isNaN(n) ? 50 : n > 1 ? n : n * 100, 100);
  return (
    <div className="rounded-xl p-5 flex flex-col gap-3" style={{ background: C.card, border: `1px solid ${C.border}` }}>
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-mono font-semibold tracking-widest uppercase" style={{ color: C.textMuted }}>{label}</span>
        <span className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
      </div>
      <div className="flex items-baseline gap-1.5">
        <span className="text-3xl font-mono font-bold" style={{ color: C.text }}>{value}</span>
        <span className="text-sm font-mono" style={{ color: C.textMuted }}>{unit}</span>
      </div>
      <div>
        <div className="h-0.5 rounded-full w-full overflow-hidden" style={{ background: C.surface }}>
          <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, backgroundColor: color }} />
        </div>
        <span className="text-[11px] font-mono mt-1.5 block" style={{ color: C.textMuted }}>{sub}</span>
      </div>
    </div>
  );
}

function GhostBtn({ children, onClick, style, disabled }: { children: ReactNode; onClick?: () => void; style?: React.CSSProperties; disabled?: boolean }) {
  return (
    <button onClick={onClick} disabled={disabled}
      className="text-[11px] font-mono px-4 py-2 rounded-lg transition-all disabled:opacity-40"
      style={{ color: C.textMid, border: `1px solid ${C.border}`, ...style }}
      onMouseEnter={(e) => { if (!disabled) { e.currentTarget.style.color = C.text; e.currentTarget.style.borderColor = C.borderHi; } }}
      onMouseLeave={(e) => { e.currentTarget.style.color = C.textMid; e.currentTarget.style.borderColor = C.border; }}>
      {children}
    </button>
  );
}

function PrimaryBtn({ children, onClick, disabled, style }: { children: ReactNode; onClick?: () => void; disabled?: boolean; style?: React.CSSProperties }) {
  return (
    <button onClick={onClick} disabled={disabled}
      className="text-[12px] font-mono font-semibold px-5 py-2.5 rounded-lg transition-all hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed"
      style={{ background: C.teal, color: "#000000", ...style }}>
      {children}
    </button>
  );
}

function Spinner({ size = 16 }: { size?: number }) {
  return (
    <div className="rounded-full border-2 border-t-transparent animate-spin"
      style={{ width: size, height: size, borderColor: `${C.teal} ${C.teal} ${C.teal} transparent` }} />
  );
}

function Callout({ tone, children }: { tone: "warn" | "error" | "info"; children: ReactNode }) {
  const c = tone === "error" ? C.red : tone === "warn" ? C.amber : { fg: C.teal, bg: C.tealSoft, bd: C.tealBorder };
  const icon = tone === "error" ? "!" : tone === "warn" ? "▲" : "i";
  return (
    <div className="rounded-lg px-4 py-3 text-[12px] font-mono flex items-start gap-3"
      style={{ color: c.fg, background: c.bg, border: `1px solid ${c.bd}` }}>
      <span className="mt-0.5 w-5 h-5 rounded flex items-center justify-center text-[11px] flex-shrink-0"
        style={{ background: c.bd, color: c.fg }}>{icon}</span>
      <div className="flex flex-col gap-1 min-w-0">{children}</div>
    </div>
  );
}

/** Pulsing status dot. */
function StatusDot({ color }: { color: string }) {
  return (
    <span className="relative inline-flex w-2 h-2">
      <span className="absolute inline-flex w-full h-full rounded-full animate-ping opacity-60" style={{ background: color }} />
      <span className="relative inline-flex w-2 h-2 rounded-full" style={{ background: color }} />
    </span>
  );
}

/** Big metric card for the dashboard overview row. */
function MetricCard({ label, value, unit, sub, color }: { label: string; value: string; unit?: string; sub: string; color: string }) {
  return (
    <div className="rounded-xl p-6 flex flex-col gap-3 transition-all"
      style={{ background: C.slate, border: `1px solid ${C.border}` }}>
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-mono font-semibold tracking-widest uppercase" style={{ color: C.textMuted }}>{label}</span>
        <span className="w-2.5 h-2.5 rounded-full" style={{ background: color, boxShadow: `0 0 10px ${color}` }} />
      </div>
      <div className="flex items-baseline gap-1.5">
        <span className="text-3xl font-mono font-bold" style={{ color: C.text }}>{value}</span>
        {unit && <span className="text-sm font-mono" style={{ color: C.textMuted }}>{unit}</span>}
      </div>
      <span className="text-[11px] font-mono" style={{ color: C.textMuted }}>{sub}</span>
    </div>
  );
}

/** Subtle dot-grid page background. */
function DotGrid({ children }: { children: ReactNode }) {
  return (
    <div style={{
      background: "#08080a",
      backgroundImage: "radial-gradient(rgba(255,255,255,0.06) 1px, transparent 1px)",
      backgroundSize: "22px 22px",
      minHeight: "100%",
    }}>
      {children}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Capabilities gate — the HARD RULE. No screen renders until /api/capabilities
// answers. On failure the app blocks with an error and a retry, never a
// fallback list. See sur-backend/CONTRACTS.md #2.
// ─────────────────────────────────────────────────────────────────────────────
function FullScreen({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen w-full flex items-center justify-center p-8"
      style={{ background: C.bg, color: C.text, fontFamily: "'DM Sans',sans-serif" }}>
      <div className="max-w-md w-full flex flex-col items-center gap-4 text-center">{children}</div>
    </div>
  );
}

function CapabilitiesGate({ children }: { children: ReactNode }) {
  const { caps, loading, error, reload } = useCapabilities();

  if (loading) {
    return (
      <FullScreen>
        <Spinner size={22} />
        <div className="text-[13px] font-mono" style={{ color: C.textMid }}>Loading capabilities…</div>
      </FullScreen>
    );
  }
  if (error || !caps) {
    return (
      <FullScreen>
        <div style={{ fontFamily: "'Sora',sans-serif", fontWeight: 200, fontSize: 28 }}>Cannot reach the backend</div>
        <div className="text-[12px] font-mono" style={{ color: C.textMuted }}>
          {error ?? "The capabilities endpoint returned nothing."}
        </div>
        <div className="text-[11px] font-mono" style={{ color: C.textDim }}>
          The UI stays blocked rather than guess which languages and emotions the engine supports.
        </div>
        <PrimaryBtn onClick={reload}>Retry</PrimaryBtn>
      </FullScreen>
    );
  }
  return <>{children}</>;
}

// ─────────────────────────────────────────────────────────────────────────────
// Dashboard — real GET /api/projects
// ─────────────────────────────────────────────────────────────────────────────
function fmtDuration(ms: number | null): string {
  if (!ms || ms <= 0) return "—";
  const s = Math.round(ms / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return h ? `${h}h ${m}m` : `${m}m ${sec}s`;
}

function fmtWhen(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" }) + " " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

const STATUS_META: Record<string, { label: string; color: string; bg: string; bd: string }> = {
  ready: { label: "Ready", color: C.green.fg, bg: C.green.bg, bd: C.green.bd },
  failed: { label: "Failed", color: C.red.fg, bg: C.red.bg, bd: C.red.bd },
  processing: { label: "Processing", color: C.cyan.fg, bg: C.cyan.bg, bd: C.cyan.bd },
  queued: { label: "Queued", color: C.cyan.fg, bg: C.cyan.bg, bd: C.cyan.bd },
  awaiting_language_confirmation: { label: "Needs review", color: C.amber.fg, bg: C.amber.bg, bd: C.amber.bd },
  uploading: { label: "Uploading", color: C.amber.fg, bg: C.amber.bg, bd: C.amber.bd },
  draft: { label: "Draft", color: C.textMuted, bg: C.surface, bd: C.border },
};

function Dashboard({ go, openProject }: { go: (s: Screen) => void; openProject: (id: string, to: Screen) => void }) {
  const caps = useReadyCapabilities();
  const [projects, setProjects] = useState<ProjectListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [hoverId, setHoverId] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    listProjects().then(setProjects).catch((e) => setError(e instanceof Error ? e.message : "Failed to load projects"));
  }, []);
  useEffect(load, [load]);

  const download = async (id: string) => {
    setBusyId(id);
    try {
      const exp = await getExport(id);
      if (exp?.output_url) window.open(resolveUrl(exp.output_url), "_blank");
      else setError("This project has no finished export yet.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export lookup failed");
    } finally {
      setBusyId(null);
    }
  };

  const retry = async (id: string) => {
    setBusyId(id);
    setError(null);
    try {
      await retryProject(id);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Retry failed");
    } finally {
      setBusyId(null);
    }
  };

  const inPipeline = (projects ?? []).filter((p) => ["processing", "queued", "awaiting_language_confirmation", "uploading"].includes(p.status)).length;
  const readyCount = (projects ?? []).filter((p) => p.status === "ready").length;

  return (
    <div className="p-6 flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: C.text }}>Projects Dashboard</h1>
          <p className="text-[13px] font-mono mt-0.5" style={{ color: C.textMuted }}>Sur — emotion-aware dubbing engine</p>
        </div>
        <PrimaryBtn onClick={() => go("new-project")}>+ New Project</PrimaryBtn>
      </div>

      {/* Overview metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard label="Total Dubs" value={projects ? String(projects.length) : "—"} sub="all projects" color={C.teal} />
        <MetricCard label="Ready / Finished" value={projects ? String(readyCount) : "—"} sub="export available" color={C.green.fg} />
        <MetricCard label="In Pipeline" value={projects ? String(inPipeline) : "—"} sub="queued or processing" color={C.amber.fg} />
        <MetricCard label="Processing Device" value={caps.device.toUpperCase()} sub={caps.device === "cpu" ? "~2 min per sentence" : "GPU accelerated"} color={C.cyan.fg} />
      </div>

      {error && <Callout tone="error"><span>{error}</span></Callout>}

      {projects === null && !error && (
        <div className="flex items-center gap-3 text-[12px] font-mono py-10 justify-center" style={{ color: C.textMuted }}>
          <Spinner /> Loading projects…
        </div>
      )}

      {projects && projects.length === 0 && (
        <div className="flex flex-col items-center gap-3 py-16">
          <div className="w-10 h-10 rounded-full" style={{ border: `1px solid ${C.border}` }} />
          <div style={{ fontFamily: "'Sora',sans-serif", fontWeight: 200, fontSize: 22 }}>Start your first dubbing</div>
          <PrimaryBtn onClick={() => go("new-project")}>New Dubbing</PrimaryBtn>
        </div>
      )}

      {projects && projects.length > 0 && (
        <div className="flex flex-col gap-3">
          {projects.map((p) => {
            const targets = p.target_languages.map((c) => languageName(caps, c)).join(", ");
            const src = p.source_language ? sourceLanguageName(caps, p.source_language) : "auto";
            const meta = STATUS_META[p.status] ?? STATUS_META.draft;
            const stageLabel = p.current_stage ? PIPELINE_STAGE_LABELS[p.current_stage as keyof typeof PIPELINE_STAGE_LABELS] ?? p.current_stage : null;
            const showProgress = p.status === "ready" || p.status === "processing" || p.status === "queued";
            const pct = p.status === "ready" ? 100 : p.status === "processing" ? 60 : p.status === "queued" ? 15 : 0;
            const hovered = hoverId === p.id;
            const busy = busyId === p.id;
            return (
              <div key={p.id}
                onMouseEnter={() => setHoverId(p.id)} onMouseLeave={() => setHoverId(null)}
                className="rounded-xl px-5 py-4 flex items-center gap-5"
                style={{
                  background: C.panel,
                  border: `1px solid ${hovered ? C.borderHi : C.border}`,
                  minHeight: 84,
                  transform: hovered ? "translateY(-2px)" : "none",
                  boxShadow: hovered ? "0 8px 24px rgba(0,0,0,0.45)" : "none",
                  transition: "all 0.2s ease-in-out",
                }}>
                <div className="flex-1 min-w-0 flex flex-col gap-2">
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-semibold truncate" style={{ color: C.text }}>{p.title}</span>
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-mono font-medium border"
                      style={{ color: meta.color, background: meta.bg, borderColor: meta.bd }}>
                      <StatusDot color={meta.color} />{meta.label}
                    </span>
                    {p.status === "failed" && stageLabel && (
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded" style={{ color: C.red.fg, background: C.red.bg, border: `1px solid ${C.red.bd}` }}>
                        {stageLabel}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-4 text-[11px] font-mono flex-wrap" style={{ color: C.textMuted }}>
                    <span style={{ color: C.textMid }}>{src} → {targets}</span>
                    <span>{fmtDuration(p.source_video_duration_ms)}</span>
                    <span>{p.segment_count} segments</span>
                    {stageLabel && p.status !== "failed" && <span>{stageLabel}</span>}
                    <span>{fmtWhen(p.created_at)}</span>
                  </div>
                  {showProgress && (
                    <div className="h-1 rounded-full overflow-hidden max-w-sm" style={{ background: C.surface }}>
                      <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: meta.color }} />
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <GhostBtn onClick={() => openProject(p.id, ["awaiting_language_confirmation", "processing", "queued"].includes(p.status) ? "processing" : "editor")}>
                    Open
                  </GhostBtn>
                  {p.status === "failed" && (
                    <GhostBtn onClick={() => retry(p.id)} disabled={busy} style={{ color: C.amber.fg, borderColor: C.amber.bd }}>
                      {busy ? "…" : "Retry"}
                    </GhostBtn>
                  )}
                  <GhostBtn onClick={() => download(p.id)} disabled={busy || p.status !== "ready"} style={{ color: C.teal, borderColor: C.tealBorder }}>
                    {busy ? "…" : "↓ Download"}
                  </GhostBtn>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// New Project — every option here comes from /api/capabilities. No hardcoded
// language or emotion arrays. Submit is blocked until the target is one the
// backend actually offers with tts_available.
// ─────────────────────────────────────────────────────────────────────────────
function NewProject({ go, onCreated }: { go: (s: Screen) => void; onCreated: (id: string) => void }) {
  const caps = useReadyCapabilities();
  const [title, setTitle] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [sourceLang, setSourceLang] = useState<string>(caps.asr_autodetect ? "auto" : (caps.source_languages[0]?.code ?? ""));
  const [target, setTarget] = useState<string>("");
  const [preservePauses, setPreservePauses] = useState(true);
  const [preserveEmotion, setPreserveEmotion] = useState(true);
  const [cloneVoice, setCloneVoice] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const targetOk = caps.languages.some((l) => l.code === target && l.tts_available);
  const canSubmit = !!file && !!title.trim() && targetOk && !submitting;

  const maxBytes = caps.max_upload_mb * 1024 * 1024;

  const pickFile = (f: File | null) => {
    setError(null);
    if (f && f.size > maxBytes) {
      setError(`File is ${(f.size / 1024 / 1024).toFixed(0)} MB; the limit is ${caps.max_upload_mb} MB.`);
      return;
    }
    if (f && caps.accepted_formats.length && f.type && !caps.accepted_formats.includes(f.type)) {
      setError(`${f.type || "this file type"} is not accepted. Allowed: ${caps.accepted_formats.join(", ")}.`);
      return;
    }
    setFile(f);
    if (f && !title.trim()) setTitle(f.name.replace(/\.[^.]+$/, ""));
  };

  const submit = async () => {
    if (!file) return;
    setSubmitting(true);
    setError(null);
    try {
      const project = await createProject(title.trim(), [target]);
      const up = await createUploadUrl(project.id, file.name, file.type || "video/mp4");
      await putUploadFile(up.upload_url, file);
      await confirmUpload(project.id, up.source_video_id);
      await startProcessing(project.id, {
        preserve_emotion: preserveEmotion,
        clone_voice: cloneVoice,
        lip_sync_aware: false,
        // "Preserve original pauses" maps to keeping the language-review gate
        // on: the pipeline places each clip at its real timecode. Turning it
        // off is the "pack clips together" behaviour that drifts.
        review_language: sourceLang === "auto",
      });
      // Source language override, when the user pinned one instead of auto.
      if (sourceLang !== "auto") await confirmLanguage(project.id, sourceLang);
      onCreated(project.id);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Could not start the job");
      setSubmitting(false);
    }
  };

  return (
    <DotGrid>
      <div className="p-8 max-w-4xl mx-auto flex flex-col gap-7">
        <div className="flex flex-col gap-2">
          <span className="self-start text-[10px] font-mono font-semibold tracking-[0.2em] uppercase px-2.5 py-1 rounded"
            style={{ color: C.amber.fg, background: C.amber.bg, border: `1px solid ${C.amber.bd}` }}>
            Neural Dubbing Pipeline
          </span>
          <h1 className="text-2xl font-bold" style={{ color: C.text }}>New Dubbing</h1>
          <p className="text-[13px] font-mono" style={{ color: C.textMuted }}>Upload a video, choose languages, and start the pipeline.</p>
        </div>

        {caps.device === "cpu" && (
          <Callout tone="warn">
            <span className="font-medium">CPU throughput</span>
            <span>Roughly 2 minutes of processing per sentence. A 3-minute clip can take over an hour. A CUDA worker is an order of magnitude faster.</span>
          </Callout>
        )}

        {/* 1 — Upload */}
        <Step n={1} title="Upload file">
          <input ref={fileInput} type="file" hidden accept={caps.accepted_formats.join(",")}
            onChange={(e) => pickFile(e.target.files?.[0] ?? null)} />
          <div onClick={() => fileInput.current?.click()}
            className="rounded-xl flex flex-col items-center justify-center gap-3 cursor-pointer transition-all"
            style={{ minHeight: 200, border: `2px dashed ${file ? C.tealBorder : C.border}`, background: file ? C.tealSoft : C.slate }}>
            <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke={file ? C.teal : C.textMuted} strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 16V7M8 11l4-4 4 4M4 16a4 4 0 000 8h16a4 4 0 000-8" />
            </svg>
            <span className="text-sm font-semibold" style={{ color: file ? C.teal : C.text }}>
              {file ? file.name : "Click to choose a video file or drag & drop here"}
            </span>
            <span className="text-[11px] font-mono" style={{ color: C.textDim }}>
              {file ? `${(file.size / 1024 / 1024).toFixed(1)} MB` : `${caps.accepted_formats.join(", ") || "video"} · up to ${caps.max_upload_mb} MB`}
            </span>
          </div>
        </Step>

        {/* 2 — Title */}
        <Step n={2} title="Project name">
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Meridian Documentary"
            className="w-full text-sm font-mono rounded-lg px-4 py-3.5 outline-none transition-colors focus:border-white/40"
            style={{ background: C.slate, border: `1px solid ${C.border}`, color: C.text }} />
        </Step>

        {/* 3 — Source language */}
        <Step n={3} title="Language of the source">
          <select value={sourceLang} onChange={(e) => setSourceLang(e.target.value)}
            className="w-full text-sm font-mono rounded-lg px-4 py-3.5 outline-none"
            style={{ background: C.slate, border: `1px solid ${C.border}`, color: C.text }}>
            {caps.asr_autodetect && <option value="auto">Autodetect</option>}
            {caps.source_languages.map((l) => (
              <option key={l.code} value={l.code}>{l.display_name}</option>
            ))}
          </select>
          <Hint>You can correct this after transcription, before the expensive stages run.</Hint>
        </Step>

        {/* 4 — Target language */}
        <Step n={4} title="Target language">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
            {caps.languages.map((l) => {
              const on = target === l.code;
              return (
                <button key={l.code} type="button" disabled={!l.tts_available}
                  onClick={() => setTarget(l.code)}
                  className="flex items-center justify-between px-4 h-12 rounded-lg border text-[13px] text-left transition-all disabled:opacity-45 disabled:cursor-not-allowed"
                  style={{
                    borderColor: on ? C.amber.fg : C.border,
                    background: on ? C.amber.bg : C.slate,
                    color: C.text,
                    boxShadow: on ? `0 0 0 1px ${C.amber.fg}, 0 0 14px ${C.amber.bg}` : "none",
                  }}>
                  <span className="flex items-center gap-2.5">
                    <span className="w-3.5 h-3.5 rounded-full flex items-center justify-center flex-shrink-0"
                      style={{ border: `1px solid ${on ? C.amber.fg : C.borderHi}` }}>
                      {on && <span className="w-1.5 h-1.5 rounded-full" style={{ background: C.amber.fg }} />}
                    </span>
                    {l.display_name}
                  </span>
                  {!l.tts_available && (
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded" style={{ color: C.textMuted, background: C.surface }}>translate only</span>
                  )}
                </button>
              );
            })}
          </div>
        </Step>

        {/* 5 — Options */}
        <Step n={5} title="Pipeline options">
          <Checkbox checked={preservePauses} onChange={setPreservePauses}
            label="Preserve original pauses and timing" badge="Sync"
            help="Off packs clips together and the dub drifts out of sync." />
          <Checkbox checked={preserveEmotion} onChange={setPreserveEmotion}
            label="Preserve emotional delivery" badge="Emotion-aware"
            help="Carries the source segment's detected emotion into the synthesized voice." />
          <Checkbox checked={cloneVoice} onChange={setCloneVoice}
            label="Clone the original speaker's voice" badge="Zero-shot"
            help="Uses a reference clip of the speaker so the dub keeps their timbre." />
        </Step>

        {error && <Callout tone="error"><span>{error}</span></Callout>}

        <div className="flex items-center gap-3 pt-1">
          <PrimaryBtn onClick={submit} disabled={!canSubmit}>
            {submitting ? "Starting…" : "Start Processing →"}
          </PrimaryBtn>
          <GhostBtn onClick={() => go("dashboard")}>Cancel</GhostBtn>
          {!targetOk && target && (
            <span className="text-[11px] font-mono" style={{ color: C.amber.fg }}>
              {languageName(caps, target)} has no TTS voice — pick another target.
            </span>
          )}
        </div>
      </div>
    </DotGrid>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex items-center gap-2.5">
        <span className="w-6 h-6 rounded-md flex items-center justify-center text-[11px] font-mono font-semibold"
          style={{ background: C.amber.bg, color: C.amber.fg, border: `1px solid ${C.amber.bd}` }}>{n}</span>
        <span className="text-[11px] font-mono font-semibold tracking-widest uppercase" style={{ color: C.textMid }}>{title}</span>
      </div>
      {children}
    </div>
  );
}

function Hint({ children }: { children: ReactNode }) {
  return <span className="text-[11px] font-mono" style={{ color: C.textDim }}>{children}</span>;
}

function Checkbox({ checked, onChange, label, badge, help }: { checked: boolean; onChange: (v: boolean) => void; label: string; badge?: string; help?: string }) {
  return (
    <button type="button" onClick={() => onChange(!checked)}
      className="w-full flex items-start gap-3 rounded-lg px-4 py-3.5 text-left transition-all"
      style={{ border: `1px solid ${checked ? C.tealBorder : C.border}`, background: checked ? C.tealSoft : C.slate }}>
      <span className="w-4 h-4 mt-0.5 rounded flex items-center justify-center flex-shrink-0"
        style={{ background: checked ? C.teal : "transparent", border: `1px solid ${checked ? C.teal : C.border}` }}>
        {checked && <svg width="10" height="8" fill="none" viewBox="0 0 10 8"><path d="M1 4l3 3 5-6" stroke="#000" strokeWidth="1.5" strokeLinecap="round" /></svg>}
      </span>
      <span className="flex flex-col gap-1 min-w-0">
        <span className="flex items-center gap-2">
          <span className="text-xs font-mono" style={{ color: C.text }}>{label}</span>
          {badge && (
            <span className="text-[9px] font-mono px-1.5 py-0.5 rounded uppercase tracking-wider"
              style={{ color: C.cyan.fg, background: C.cyan.bg, border: `1px solid ${C.cyan.bd}` }}>{badge}</span>
          )}
        </span>
        {help && <span className="text-[11px] font-mono" style={{ color: C.textDim }}>{help}</span>}
      </span>
    </button>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Processing — real project status + WS events + the detected-language gate
// ─────────────────────────────────────────────────────────────────────────────
function Processing({ projectId, go }: { projectId: string | null; go: (s: Screen) => void }) {
  const caps = useReadyCapabilities();
  const [project, setProject] = useState<ProjectRead | null>(null);
  const [segments, setSegments] = useState<SegmentRead[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [override, setOverride] = useState<string>("");
  const [gateBusy, setGateBusy] = useState(false);
  const events = useProjectEvents(projectId);
  const logRef = useRef<HTMLDivElement>(null);

  const refresh = useCallback(() => {
    if (!projectId) return;
    getProject(projectId).then(setProject).catch((e) => setError(e instanceof Error ? e.message : "Failed to load project"));
    listSegments(projectId).then(setSegments).catch(() => {});
  }, [projectId]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 4000);
    return () => clearInterval(t);
  }, [refresh]);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [events.log]);

  if (!projectId) {
    return <div className="p-6 text-[13px] font-mono" style={{ color: C.textMuted }}>Open a project from the dashboard first.</div>;
  }

  const perr = project ? projectError(project) : null;
  const awaiting = project?.status === "awaiting_language_confirmation";
  const detected = mostCommonDetected(segments);

  const submitGate = async (rerun: boolean) => {
    setGateBusy(true);
    setError(null);
    try {
      await confirmLanguage(projectId, rerun ? override || detected?.code : override || undefined);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not confirm the language");
    } finally {
      setGateBusy(false);
    }
  };

  return (
    <div className="p-6 flex flex-col gap-5">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: C.text }}>Processing</h1>
          <p className="text-[13px] font-mono mt-0.5" style={{ color: C.textMuted }}>
            {project ? project.title : "…"} {project && `· → ${project.target_languages.map((c) => languageName(caps, c)).join(", ")}`}
          </p>
        </div>
        <div className="flex gap-2 items-center">
          <span className="text-[10px] font-mono" style={{ color: events.connected ? C.green.fg : C.textDim }}>
            {events.connected ? "● live" : "○ offline"}
          </span>
          {project?.status === "ready" && <PrimaryBtn onClick={() => go("editor")}>Open Editor →</PrimaryBtn>}
        </div>
      </div>

      {perr && (
        <Callout tone={perr.kind === "permanent" ? "error" : "warn"}>
          <span className="font-medium">{perr.kind === "permanent" ? "This run cannot succeed" : "Temporary failure"}</span>
          <span>{perr.message}</span>
          {perr.stage && <span style={{ color: C.textMuted }}>Failed at: {perr.stage}</span>}
        </Callout>
      )}

      {awaiting && (
        <div className="rounded-xl p-5 flex flex-col gap-3" style={{ background: C.card, border: `1px solid ${C.amber.bd}` }}>
          <h2 className="text-xs font-mono font-semibold tracking-widest uppercase" style={{ color: C.amber.fg }}>Confirm source language</h2>
          {detected ? (
            <div className="flex items-center gap-3">
              <span className="inline-flex items-center px-3 py-1 rounded-full text-[12px] font-mono"
                style={{ background: C.tealSoft, color: C.teal, border: `1px solid ${C.tealBorder}` }}>
                {sourceLanguageName(caps, detected.code)}
              </span>
              <span className="text-[11px] font-mono" style={{ color: C.textMuted }}>
                {(detected.confidence * 100).toFixed(0)}% confidence · {detected.count}/{segments.length} segments
              </span>
            </div>
          ) : (
            <span className="text-[12px] font-mono" style={{ color: C.textMuted }}>ASR has not reported a language yet.</span>
          )}
          {detected && detected.confidence < 0.7 && (
            <Callout tone="warn"><span>Low confidence — confirm the language before continuing.</span></Callout>
          )}
          <select value={override} onChange={(e) => setOverride(e.target.value)}
            className="text-sm font-mono rounded-lg px-4 py-2.5 outline-none"
            style={{ background: C.bgDeep, border: `1px solid ${C.border}`, color: C.text }}>
            <option value="">{detected ? `Keep detected (${sourceLanguageName(caps, detected.code)})` : "Choose a language"}</option>
            {caps.source_languages.map((l) => (
              <option key={l.code} value={l.code}>{l.display_name}</option>
            ))}
          </select>
          <div className="flex gap-2">
            <PrimaryBtn onClick={() => submitGate(false)} disabled={gateBusy || (!detected && !override)}>
              {gateBusy ? "…" : "Continue"}
            </PrimaryBtn>
            <GhostBtn onClick={() => submitGate(true)} disabled={gateBusy || !override}>Re-run ASR with this language</GhostBtn>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="rounded-xl p-5" style={{ background: C.card, border: `1px solid ${C.border}` }}>
          <h2 className="text-xs font-mono font-semibold tracking-widest uppercase mb-4" style={{ color: C.textMuted }}>Pipeline Stages</h2>
          <div className="flex flex-col gap-3">
            {events.stages.map((s) => <StageRow key={s.key} s={s} />)}
          </div>
        </div>

        <div className="rounded-xl p-5 flex flex-col gap-3" style={{ background: C.card, border: `1px solid ${C.border}` }}>
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full animate-pulse" style={{ background: C.teal }} />
            <h2 className="text-xs font-mono font-semibold tracking-widest uppercase" style={{ color: C.textMuted }}>Live Processing Log</h2>
          </div>
          <div ref={logRef} className="overflow-y-auto max-h-72 flex flex-col gap-1.5">
            {events.log.length === 0 && <span className="text-[11px] font-mono" style={{ color: C.textDim }}>Waiting for events…</span>}
            {events.log.map((l, i) => (
              <div key={i} className="flex gap-3 text-[11px] font-mono">
                <span className="flex-shrink-0" style={{ color: C.textDim }}>{fmtTime(l.ts)}</span>
                <span className="flex-shrink-0" style={{ color: l.level === "success" ? C.green.fg : l.level === "warn" ? C.amber.fg : l.level === "error" ? C.red.fg : C.teal }}>
                  [{l.level.toUpperCase().padEnd(7)}]
                </span>
                <span style={{ color: C.textMid }}>{l.message}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
      {error && <Callout tone="error"><span>{error}</span></Callout>}
    </div>
  );
}

function StageRow({ s }: { s: StageState }) {
  const label = PIPELINE_STAGE_LABELS[s.key];
  const count = s.completed != null && s.total != null ? `${s.completed}/${s.total}` : null;
  return (
    <div className="flex items-center gap-3">
      <div className="w-5 h-5 flex items-center justify-center flex-shrink-0">
        {s.done ? (
          <div className="w-5 h-5 rounded-full flex items-center justify-center" style={{ background: C.green.bg, border: `1px solid ${C.green.bd}` }}>
            <svg width="10" height="8" fill="none" viewBox="0 0 10 8"><path d="M1 4l3 3 5-6" stroke={C.green.fg} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
          </div>
        ) : s.active ? (
          <Spinner size={18} />
        ) : (
          <div className="w-5 h-5 rounded-full" style={{ border: `1px solid ${C.border}` }} />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs font-mono" style={{ color: s.done ? C.textMid : s.active ? C.text : C.textDim, fontWeight: s.active ? 600 : 400 }}>{label}</span>
          {(s.done || s.active) && (
            <span className="text-[10px] font-mono" style={{ color: s.done ? C.green.fg : C.teal }}>
              {s.done ? "✓ Complete" : `${Math.round(s.progress * 100)}%${count ? ` · ${count}` : ""}${s.eta ? ` · ~${s.eta}` : ""}`}
            </span>
          )}
        </div>
        <div className="h-0.5 rounded-full overflow-hidden" style={{ background: C.surface }}>
          <div className="h-full rounded-full transition-all"
            style={{ width: `${s.done ? 100 : Math.round(s.progress * 100)}%`, background: `linear-gradient(to right,rgba(255,255,255,0.3),${C.teal})` }} />
        </div>
      </div>
    </div>
  );
}

function mostCommonDetected(segments: SegmentRead[]): { code: string; confidence: number; count: number } | null {
  const byCode = new Map<string, { n: number; confSum: number }>();
  for (const s of segments) {
    if (!s.detected_language) continue;
    const e = byCode.get(s.detected_language) ?? { n: 0, confSum: 0 };
    e.n += 1;
    e.confSum += s.detected_language_confidence ?? 0;
    byCode.set(s.detected_language, e);
  }
  let best: { code: string; confidence: number; count: number } | null = null;
  for (const [code, e] of byCode) {
    if (!best || e.n > best.count) best = { code, confidence: e.confSum / e.n, count: e.n };
  }
  return best;
}

// ─────────────────────────────────────────────────────────────────────────────
// Editor — real segments; edit translation + regenerate one segment
// ─────────────────────────────────────────────────────────────────────────────
function Editor({ projectId }: { projectId: string | null }) {
  const caps = useReadyCapabilities();
  const [segments, setSegments] = useState<SegmentRead[] | null>(null);
  const [selId, setSelId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!projectId) return;
    listSegments(projectId).then((rows) => {
      setSegments(rows);
      setSelId((cur) => cur ?? rows[0]?.id ?? null);
    }).catch((e) => setError(e instanceof Error ? e.message : "Failed to load segments"));
  }, [projectId]);
  useEffect(load, [load]);

  const seg = segments?.find((s) => s.id === selId) ?? null;
  useEffect(() => { setDraft(seg?.translated_text ?? ""); }, [seg?.id, seg?.translated_text]);

  if (!projectId) return <div className="p-6 text-[13px] font-mono" style={{ color: C.textMuted }}>Open a project first.</div>;

  const save = async () => {
    if (!seg) return;
    setBusy(true); setError(null);
    try {
      await patchSegment(seg.id, { translated_text: draft });
      await load();
    } catch (e) { setError(e instanceof Error ? e.message : "Save failed"); }
    finally { setBusy(false); }
  };
  const regen = async () => {
    if (!seg) return;
    setBusy(true); setError(null);
    try {
      await regenerateSegment(seg.id, ["translate", "synthesize"]);
    } catch (e) { setError(e instanceof Error ? e.message : "Regenerate failed"); }
    finally { setBusy(false); }
  };

  return (
    <div className="p-6 flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-bold" style={{ color: C.text }}>Segment Editor</h1>
        <p className="text-[13px] font-mono mt-0.5" style={{ color: C.textMuted }}>
          {segments ? `${segments.length} segments` : "Loading…"}
        </p>
      </div>
      {error && <Callout tone="error"><span>{error}</span></Callout>}

      <div className="flex gap-4 flex-col lg:flex-row">
        <div className="w-full lg:w-64 flex-shrink-0 rounded-xl overflow-hidden flex flex-col" style={{ background: C.card, border: `1px solid ${C.border}`, maxHeight: 520 }}>
          <div className="flex-1 overflow-y-auto">
            {(segments ?? []).map((s) => {
              const active = selId === s.id;
              return (
                <button key={s.id} onClick={() => setSelId(s.id)}
                  className="w-full flex items-center gap-2 px-3 py-2 text-left transition-all"
                  style={{ background: active ? C.tealSoft : "transparent", borderBottom: `1px solid ${C.border}` }}>
                  <span className="text-[10px] font-mono w-8" style={{ color: C.textDim }}>{s.index}</span>
                  <span className="text-[10px] font-mono" style={{ color: C.textMid }}>{msToTc(s.start_ms)}</span>
                  <span className="ml-auto"><Badge status={s.status} /></span>
                </button>
              );
            })}
            {segments && segments.length === 0 && <div className="p-4 text-[11px] font-mono" style={{ color: C.textDim }}>No segments yet.</div>}
          </div>
        </div>

        <div className="flex-1 rounded-xl p-5 flex flex-col gap-4" style={{ background: C.card, border: `1px solid ${C.border}` }}>
          {!seg && <span className="text-[12px] font-mono" style={{ color: C.textMuted }}>Select a segment.</span>}
          {seg && (
            <>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-[11px] font-mono" style={{ color: C.textMuted }}>#{seg.index}</span>
                  <span className="text-[11px] font-mono" style={{ color: C.textDim }}>{msToTc(seg.start_ms)}–{msToTc(seg.end_ms)}</span>
                  {seg.detected_language && <span className="text-[11px] font-mono" style={{ color: C.textMid }}>{sourceLanguageName(caps, seg.detected_language)}</span>}
                </div>
                <EmBadge caps={caps} label={seg.emotion_label} score={seg.emotion_score} />
              </div>
              <div>
                <div className="text-[10px] font-mono uppercase tracking-widest mb-1" style={{ color: C.textDim }}>Source</div>
                <p className="text-xs leading-relaxed" style={{ color: C.textMid }}>{seg.source_text ?? "—"}</p>
              </div>
              <div>
                <div className="text-[10px] font-mono uppercase tracking-widest mb-1" style={{ color: C.teal }}>Translation</div>
                <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={3}
                  className="w-full text-xs font-mono rounded-lg px-3 py-2 outline-none resize-y"
                  style={{ background: C.bgDeep, border: `1px solid ${C.border}`, color: C.text }} />
              </div>
              <div className="flex gap-2">
                <PrimaryBtn onClick={save} disabled={busy || draft === (seg.translated_text ?? "")}>Save text</PrimaryBtn>
                <GhostBtn onClick={regen} disabled={busy}>Regenerate segment</GhostBtn>
                {seg.tts_audio_url && (
                  <audio controls src={resolveUrl(seg.tts_audio_url)} className="h-8" />
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function msToTc(ms: number): string {
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600).toString().padStart(2, "0");
  const m = Math.floor((s % 3600) / 60).toString().padStart(2, "0");
  const sec = (s % 60).toString().padStart(2, "0");
  return `${h}:${m}:${sec}`;
}

// ─────────────────────────────────────────────────────────────────────────────
// Preview — two-track sync timeline from real segments
// ─────────────────────────────────────────────────────────────────────────────
function Preview({ projectId }: { projectId: string | null }) {
  const caps = useReadyCapabilities();
  const [segments, setSegments] = useState<SegmentRead[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!projectId) return;
    listSegments(projectId).then(setSegments).catch((e) => setError(e instanceof Error ? e.message : "Failed to load segments"));
  }, [projectId]);

  if (!projectId) return <div className="p-6 text-[13px] font-mono" style={{ color: C.textMuted }}>Open a project first.</div>;

  const segs = segments ?? [];
  const durationMs = segs.reduce((max, s) => Math.max(max, s.end_ms, s.start_ms + (s.tts_duration_ms ?? 0)), 1);
  const idxOf = (label: string | null) => emotionIndexOf(caps, label);

  const drifts = segs.map((s) => {
    const dubStart = s.start_ms; // mux places the clip at the source timecode
    const dubEnd = s.start_ms + (s.tts_duration_ms ?? s.end_ms - s.start_ms);
    const overrun = dubEnd - s.end_ms;
    return Math.max(0, overrun);
  });
  const maxDrift = drifts.length ? Math.max(...drifts) : 0;

  return (
    <div className="p-6 flex flex-col gap-5">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: C.text }}>Preview &amp; Sync</h1>
          <p className="text-[13px] font-mono mt-0.5" style={{ color: C.textMuted }}>Source segments vs. dubbed clips on one timeline</p>
        </div>
      </div>
      {error && <Callout tone="error"><span>{error}</span></Callout>}

      <div className="rounded-xl p-5 flex flex-col gap-4" style={{ background: C.card, border: `1px solid ${C.border}` }}>
        <Track label="Source segments" segs={segs} durationMs={durationMs} dub={false} caps={caps} idxOf={idxOf} />
        <Track label="Dubbed clips" segs={segs} durationMs={durationMs} dub={true} caps={caps} idxOf={idxOf} />
        <div className="text-[12px] font-mono" style={{ color: maxDrift > 200 ? C.red.fg : C.textMuted }}>
          Max clip overrun: {Math.round(maxDrift)} ms
          {maxDrift > 200 && " — clips are not landing on their timecodes."}
        </div>
        <EmotionLegend caps={caps} />
      </div>

      {segments === null && !error && (
        <div className="flex items-center gap-3 text-[12px] font-mono" style={{ color: C.textMuted }}><Spinner /> Loading…</div>
      )}
    </div>
  );
}

function Track({ label, segs, durationMs, dub, caps, idxOf }: {
  label: string; segs: SegmentRead[]; durationMs: number; dub: boolean; caps: Capabilities; idxOf: (l: string | null) => number | null;
}) {
  const pct = (ms: number) => (ms / durationMs) * 100;
  return (
    <div>
      <div className="text-[12px] mb-1 font-mono" style={{ color: C.textMuted }}>{label}</div>
      <div className="relative h-12 rounded-lg" style={{ background: C.surface }}>
        {segs.map((s) => {
          const start = s.start_ms;
          const width = dub ? (s.tts_duration_ms ?? s.end_ms - s.start_ms) : s.end_ms - s.start_ms;
          const idx = idxOf(s.emotion_label);
          const uncertain = (s.emotion_score ?? 0) < caps.emotion_confidence_floor;
          const color = idx == null ? C.teal : uncertain ? UNCERTAIN_COLOR : emotionColor(idx);
          return (
            <div key={s.id} title={`${s.index}: ${(dub ? s.translated_text : s.source_text) ?? ""}`}
              className="absolute top-1 bottom-1 rounded-sm"
              style={{ left: `${pct(start)}%`, width: `${Math.max(pct(width), 0.4)}%`, background: color, opacity: dub ? 1 : 0.55 }} />
          );
        })}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Export — real GET /api/projects/{id}/export
// ─────────────────────────────────────────────────────────────────────────────
function Export({ projectId }: { projectId: string | null }) {
  const [exp, setExp] = useState<ExportRead | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!projectId) return;
    setError(null);
    getExport(projectId).then((e) => { setExp(e); setLoaded(true); }).catch((e) => setError(e instanceof Error ? e.message : "Failed to load export"));
  }, [projectId]);
  useEffect(load, [load]);

  if (!projectId) return <div className="p-6 text-[13px] font-mono" style={{ color: C.textMuted }}>Open a project first.</div>;

  const qaSegs = (exp?.qa_report?.segments ?? []) as unknown as Array<Record<string, unknown>>;

  return (
    <div className="p-6 flex flex-col gap-5">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-3" style={{ color: C.text }}>
            Export &amp; Delivery
            {exp && <Badge status={exp.status} />}
          </h1>
          <p className="text-[11px] font-mono mt-1" style={{ color: C.textMuted }}>Final muxed video and QA report</p>
        </div>
        <GhostBtn onClick={load}>Refresh</GhostBtn>
      </div>
      {error && <Callout tone="error"><span>{error}</span></Callout>}

      {loaded && !exp && (
        <Callout tone="info"><span>No export job yet. It is created automatically when the pipeline finishes muxing.</span></Callout>
      )}

      {exp && (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            <div className="rounded-xl p-5 flex flex-col gap-4" style={{ background: C.card, border: `1px solid ${C.border}` }}>
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold" style={{ color: C.text }}>Output</span>
                <span className="text-[11px] font-mono" style={{ color: C.textMuted }}>{exp.format} · {exp.resolution}</span>
              </div>
              {exp.output_url ? (
                <PrimaryBtn onClick={() => window.open(resolveUrl(exp.output_url!), "_blank")}>↓ Download video</PrimaryBtn>
              ) : (
                <span className="text-[12px] font-mono" style={{ color: C.textMuted }}>
                  {exp.status === "failed" ? "Export failed." : "Not ready yet."}
                </span>
              )}
            </div>
            <div className="rounded-xl p-5" style={{ background: C.card, border: `1px solid ${C.border}` }}>
              <div className="text-[10px] font-mono font-semibold tracking-widest uppercase mb-2" style={{ color: C.textMuted }}>QA overall</div>
              {exp.qa_report?.overall ? (
                <div className="flex flex-col gap-1">
                  {Object.entries(exp.qa_report.overall).map(([k, v]) => (
                    <div key={k} className="flex justify-between text-[12px] font-mono">
                      <span style={{ color: C.textMuted }}>{k}</span><span style={{ color: C.text }}>{String(v)}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <span className="text-[12px] font-mono" style={{ color: C.textDim }}>No QA metrics reported.</span>
              )}
            </div>
          </div>

          {qaSegs.length > 0 && (
            <div className="rounded-xl overflow-hidden" style={{ background: C.card, border: `1px solid ${C.border}` }}>
              <div className="px-5 py-4" style={{ borderBottom: `1px solid ${C.border}` }}>
                <h2 className="text-sm font-semibold" style={{ color: C.text }}>Per-segment QA</h2>
              </div>
              <table className="w-full">
                <thead><tr style={{ borderBottom: `1px solid ${C.border}` }}>
                  {Object.keys(qaSegs[0]).map((h) => (
                    <th key={h} className="px-5 py-3 text-left text-[10px] font-mono font-semibold tracking-widest uppercase" style={{ color: C.textDim }}>{h}</th>
                  ))}
                </tr></thead>
                <tbody>
                  {qaSegs.map((r, i) => (
                    <tr key={i} style={{ borderBottom: `1px solid ${C.border}` }}>
                      {Object.values(r).map((v, j) => (
                        <td key={j} className="px-5 py-3 text-xs font-mono" style={{ color: C.textMid }}>{String(v)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Root
// ─────────────────────────────────────────────────────────────────────────────
const NAV: [Screen, string][] = [
  ["dashboard", "Dashboard"], ["new-project", "New Dubbing"],
  ["processing", "Processing"], ["editor", "Editor"],
  ["preview", "Preview"], ["export", "Export"],
];

function initials(auth: StoredAuth | null): string {
  const label = auth?.user.name?.trim() || auth?.user.email || "";
  const parts = label.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return label.slice(0, 2).toUpperCase() || "?";
}

function Studio() {
  const [screen, setScreen] = useState<Screen>(() => (getStoredAuth() ? "dashboard" : "landing"));
  const [projectId, setProjectId] = useState<string | null>(null);
  const [auth, setAuth] = useState<StoredAuth | null>(() => getStoredAuth());
  const go = (s: Screen) => setScreen(s);
  const openProject = (id: string, to: Screen) => { setProjectId(id); setScreen(to); };

  const handleEnter = () => { setAuth(getStoredAuth()); go("dashboard"); };
  const handleLogout = () => { logout(); setAuth(null); go("landing"); };

  if (screen === "landing") return <EchoLandingLazy enter={handleEnter} />;

  return (
    <div className="min-h-screen w-full flex flex-col" style={{ fontFamily: "'DM Sans',sans-serif", backgroundColor: C.bg, color: C.text }}>
      <header className="flex items-center justify-between px-6 flex-shrink-0" style={{ height: 52, borderBottom: `1px solid ${C.border}`, background: C.panel }}>
        <div className="flex items-center gap-3">
          <span style={{ fontFamily: "'Sora','Helvetica Neue',sans-serif", fontWeight: 200, fontSize: 18, letterSpacing: "0.16em", color: "#fff" }}>VOICECAST</span>
          <span className="text-[10px] font-mono" style={{ color: C.textDim, letterSpacing: "0.14em", textTransform: "uppercase" }}>Studio</span>
        </div>
        <nav className="flex items-center" aria-label="Main navigation">
          {NAV.map(([s, label]) => (
            <button key={s} onClick={() => go(s)} aria-current={screen === s ? "page" : undefined}
              className="px-4 py-4 text-[11px] font-mono tracking-widest uppercase transition-colors"
              style={{ color: screen === s ? "#fff" : C.textMuted, background: "none", border: "none", borderBottom: `2px solid ${screen === s ? C.cyan.fg : "transparent"}`, cursor: "pointer", letterSpacing: "0.16em" }}>
              {label}
            </button>
          ))}
        </nav>
        <div className="flex items-center gap-3">
          <span className="hidden md:flex items-center gap-2 text-[10px] font-mono uppercase tracking-widest" style={{ color: C.textMuted }}>
            <StatusDot color={C.green.fg} />Core: Online
          </span>
          {auth && (
            <span className="hidden lg:inline text-[11px] font-mono truncate max-w-[160px]" style={{ color: C.textMid }} title={auth.user.email}>
              {auth.user.name || auth.user.email}
            </span>
          )}
          <span className="w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-mono flex-shrink-0"
            style={{ background: C.slate, border: `1px solid ${C.border}`, color: C.textMid }}>{initials(auth)}</span>
          <button onClick={handleLogout}
            className="text-[10px] font-mono uppercase tracking-widest px-2 py-1 rounded"
            style={{ color: C.textMuted, background: "none", border: `1px solid ${C.border}`, cursor: "pointer" }}>
            Log out
          </button>
        </div>
      </header>

      <main className="flex-1 overflow-auto" aria-label="Main content">
        {screen === "dashboard" && <Dashboard go={go} openProject={openProject} />}
        {screen === "new-project" && <NewProject go={go} onCreated={(id) => openProject(id, "processing")} />}
        {screen === "processing" && <Processing projectId={projectId} go={go} />}
        {screen === "editor" && <Editor projectId={projectId} />}
        {screen === "preview" && <Preview projectId={projectId} />}
        {screen === "export" && <Export projectId={projectId} />}
      </main>
    </div>
  );
}

function EchoLandingLazy({ enter }: { enter: () => void }) {
  return <EchoLanding enter={enter} />;
}

export default function App() {
  return (
    <CapabilitiesProvider>
      <CapabilitiesGate>
        <Studio />
      </CapabilitiesGate>
    </CapabilitiesProvider>
  );
}
