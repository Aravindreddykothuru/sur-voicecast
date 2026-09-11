/**
 * Screen 3: Project detail. Composes the four real-time panels: progress,
 * the detected-language gate, the sync timeline, and errors -- plus a
 * download link once the project is ready (GET /api/projects/{id}/export).
 */
import { useCallback, useEffect, useState } from "react";
import { confirmLanguage, getExport, getProject, listSegments, resolveUrl, startProcessing } from "../lib/api";
import { PipelineProgress } from "../components/PipelineProgress";
import { DetectedLanguageGate } from "../components/DetectedLanguageGate";
import { SyncTimeline } from "../components/SyncTimeline";
import { ErrorPanel } from "../components/ErrorPanel";
import { useProjectEvents } from "../lib/useProjectEvents";
import { projectError, type ExportRead, type ProjectRead, type SegmentRead } from "../lib/types";

export function ProjectDetailScreen({ projectId }: { projectId: string }) {
  const [project, setProject] = useState<ProjectRead | null>(null);
  const [segments, setSegments] = useState<SegmentRead[]>([]);
  const [exportJob, setExportJob] = useState<ExportRead | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const events = useProjectEvents(projectId);

  const reload = useCallback(() => {
    getProject(projectId)
      .then(setProject)
      .catch((e: unknown) => setLoadError(e instanceof Error ? e.message : "Could not load this project"));
    listSegments(projectId).then(setSegments).catch(() => {});
  }, [projectId]);

  useEffect(reload, [reload]);

  // Re-poll on any pipeline event so status/stage/segments stay current --
  // the WebSocket tells us *something* changed, this fetches what.
  useEffect(() => {
    if (events.log.length > 0 || events.lastSegmentReady) reload();
  }, [events.log.length, events.lastSegmentReady, reload]);

  useEffect(() => {
    if (project?.status === "ready") {
      getExport(projectId).then(setExportJob).catch(() => {});
    } else {
      setExportJob(null);
    }
  }, [project?.status, projectId]);

  if (loadError) {
    return (
      <div className="panel p-6 text-body" role="alert" style={{ color: "var(--err)" }}>
        {loadError}
      </div>
    );
  }
  if (!project) return <p className="text-meta">Loading…</p>;

  const detectedSegment = segments.find((s) => s.detected_language);
  const error = projectError(project);

  async function handleConfirm(overrideCode?: string) {
    setConfirming(true);
    try {
      await confirmLanguage(projectId, overrideCode);
      reload();
    } finally {
      setConfirming(false);
    }
  }

  async function handleRetry() {
    if (!project) return;
    setRetrying(true);
    try {
      await startProcessing(projectId, {
        preserve_emotion: project.preserve_emotion,
        clone_voice: project.clone_voice,
        lip_sync_aware: project.lip_sync_aware,
        tts_model: project.tts_model,
        review_language: project.review_language,
      });
      reload();
    } finally {
      setRetrying(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="panel flex items-center justify-between p-5">
        <div>
          <p className="text-page-title">{project.title}</p>
          <p className="text-meta">Status: {project.status}</p>
        </div>
        {exportJob?.output_url && (
          <a className="btn-primary" href={resolveUrl(exportJob.output_url)} target="_blank" rel="noreferrer">
            Download
          </a>
        )}
      </div>

      {/* Errors clear the instant the project leaves the failed state --
          projectError() returns null for any other status, so there is no
          separate "clear" action to wire up. */}
      {error && <ErrorPanel error={error} onRetry={handleRetry} retrying={retrying} />}

      {project.status === "awaiting_language_confirmation" && (
        <DetectedLanguageGate
          project={project}
          detectedLanguage={detectedSegment?.detected_language ?? null}
          detectedConfidence={detectedSegment?.detected_language_confidence ?? null}
          onConfirm={handleConfirm}
          onRerunAsr={handleConfirm}
          submitting={confirming}
        />
      )}

      <PipelineProgress stages={events.stages} />

      <SyncTimeline segments={segments} />
    </div>
  );
}
