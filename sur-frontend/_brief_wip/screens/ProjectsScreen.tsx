/**
 * Screen 1: Projects list + empty state.
 *
 * Empty state: centered mark + "Start your first dubbing" + two tiles
 * (New Dubbing, Upload a file) -- not three. This app has no folders, so a
 * third "New folder" tile (as a reference product might show) has nothing
 * real to do.
 */
import { useCallback, useEffect, useState } from "react";
import { listProjects } from "../lib/api";
import { useReadyCapabilities, languageName, sourceLanguageName } from "../lib/capabilities";
import type { ProjectListItem } from "../lib/types";

function StageBadge({ project }: { project: ProjectListItem }) {
  const map: Record<string, { label: string; color: string }> = {
    draft: { label: "Draft", color: "var(--text-muted)" },
    uploading: { label: "Uploading", color: "var(--warn)" },
    queued: { label: "Queued", color: "var(--warn)" },
    processing: { label: project.current_stage ? `Processing · ${project.current_stage}` : "Processing", color: "var(--warn)" },
    awaiting_language_confirmation: { label: "Needs confirmation", color: "var(--warn)" },
    ready: { label: "Ready", color: "var(--ok)" },
    failed: { label: "Failed", color: "var(--err)" },
  };
  const entry = map[project.status] ?? { label: project.status, color: "var(--text-muted)" };
  return (
    <span
      className="rounded-full px-2 py-0.5 text-meta font-medium"
      style={{ background: "color-mix(in srgb, " + entry.color + " 14%, transparent)", color: entry.color }}
    >
      {entry.label}
    </span>
  );
}

function formatCreatedAt(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

function EmptyState({ onNewDubbing }: { onNewDubbing: () => void }) {
  return (
    <div className="panel flex flex-col items-center gap-6 p-16 text-center">
      <div
        className="flex h-14 w-14 items-center justify-center rounded-2xl text-lg font-semibold"
        style={{ background: "var(--accent)", color: "var(--text-on-accent)" }}
      >
        S
      </div>
      <div className="flex flex-col gap-1">
        <p className="text-section-title">Start your first dubbing</p>
        <p className="text-meta">Upload a video and Sur will transcribe, translate, and re-voice it.</p>
      </div>
      <div className="flex gap-3">
        <button className="btn-primary" onClick={onNewDubbing}>
          New Dubbing
        </button>
        <button className="btn-secondary" onClick={onNewDubbing}>
          Upload a file
        </button>
      </div>
    </div>
  );
}

export function ProjectsScreen({
  onNewDubbing,
  onOpenProject,
}: {
  onNewDubbing: () => void;
  onOpenProject: (projectId: string) => void;
}) {
  const caps = useReadyCapabilities();
  const [projects, setProjects] = useState<ProjectListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    listProjects()
      .then((p) => {
        setProjects(p);
        setError(null);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Could not load projects"));
  }, []);

  useEffect(() => {
    reload();
    // Light polling so stage/status badges don't go stale while this screen
    // is left open -- every value shown still comes straight from the
    // backend, this just re-asks it.
    const id = setInterval(reload, 8000);
    return () => clearInterval(id);
  }, [reload]);

  if (error) {
    return (
      <div className="panel p-6 text-body" role="alert" style={{ color: "var(--err)" }}>
        {error}
      </div>
    );
  }

  if (projects === null) {
    return <p className="text-meta">Loading projects…</p>;
  }

  if (projects.length === 0) {
    return <EmptyState onNewDubbing={onNewDubbing} />;
  }

  return (
    <div className="panel overflow-hidden">
      {projects.map((p) => (
        <button
          key={p.id}
          onClick={() => onOpenProject(p.id)}
          className="flex w-full items-center justify-between px-5 py-4 text-left transition-colors"
          style={{ borderBottom: "1px solid var(--border)" }}
          onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-hover)")}
          onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
        >
          <div className="flex min-w-0 flex-col gap-1">
            <span className="text-body font-medium">{p.title}</span>
            <span className="text-meta">
              {p.source_language ? sourceLanguageName(caps, p.source_language) : "Auto-detect"} →{" "}
              {p.target_languages.map((code) => languageName(caps, code)).join(", ")}
              {" · "}
              {formatCreatedAt(p.created_at)}
            </span>
          </div>
          <div className="flex items-center gap-3">
            <StageBadge project={p} />
            <span className="text-label" style={{ color: "var(--text-secondary)" }}>
              {p.status === "ready" ? "Download" : "Open"}
            </span>
          </div>
        </button>
      ))}
    </div>
  );
}
