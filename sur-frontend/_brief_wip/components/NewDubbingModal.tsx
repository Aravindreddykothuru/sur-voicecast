/**
 * Screen 2: New Dubbing modal.
 *
 * Deliberately NOT wired: a "speaker number" field (this app doesn't
 * diarize by speaker count -- dropped per spec) and a "preserve original
 * pauses and timing" toggle. The latter has no backend to turn off: the mux
 * stage (app/pipeline/ffmpeg_utils.py mux_timeline) always places every
 * clip at its source timecode -- that replaced the naive back-to-back
 * concatenation that used to drift out of sync, and there is no
 * ProcessRequest field to bring the old behavior back. Rendering a checkbox
 * for it would offer a control with no effect, which is worse than not
 * having it. See the gap list in the final report.
 */
import { useState } from "react";
import { confirmUpload, createProject, createUploadUrl, putUploadFile, startProcessing, type ProcessOptions } from "../lib/api";
import { useReadyCapabilities } from "../lib/capabilities";
import { LanguageMultiSelect } from "./LanguageMultiSelect";

interface NewDubbingModalProps {
  onClose: () => void;
  onCreated: (projectId: string) => void;
}

function StepLabel({ n, children }: { n: number; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span
        className="flex h-5 w-5 items-center justify-center rounded-full text-meta font-semibold"
        style={{ background: "var(--accent)", color: "var(--text-on-accent)" }}
      >
        {n}
      </span>
      <span className="text-label">{children}</span>
    </div>
  );
}

export function NewDubbingModal({ onClose, onCreated }: NewDubbingModalProps) {
  const caps = useReadyCapabilities();
  const [file, setFile] = useState<File | null>(null);
  const [confirmAfterAsr, setConfirmAfterAsr] = useState(true);
  const [targets, setTargets] = useState<string[]>([]);
  const [preserveEmotion, setPreserveEmotion] = useState(true);
  const [cloneVoice, setCloneVoice] = useState(false);
  const [lipSyncAware, setLipSyncAware] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const validTargets = targets.filter((code) => {
    const lang = caps.languages.find((l) => l.code === code);
    return lang && lang.tts_available;
  });
  const fileTooLarge = !!file && file.size > caps.max_upload_mb * 1024 * 1024;
  const formatAccepted = !!file && caps.accepted_formats.includes(file.type);
  const canSubmit = !!file && !fileTooLarge && formatAccepted && validTargets.length > 0 && !submitting;

  async function handleSubmit() {
    if (!file || !canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const project = await createProject(file.name.replace(/\.[^.]+$/, ""), validTargets);
      const upload = await createUploadUrl(project.id, file.name, file.type);
      await putUploadFile(upload.upload_url, file);
      await confirmUpload(project.id, upload.source_video_id, undefined);

      const opts: ProcessOptions = {
        preserve_emotion: preserveEmotion,
        clone_voice: cloneVoice,
        lip_sync_aware: lipSyncAware,
        review_language: confirmAfterAsr,
      };
      await startProcessing(project.id, opts);
      onCreated(project.id);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Could not start this dub");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(28, 25, 23, 0.4)" }}
      onClick={onClose}
    >
      <div
        className="panel flex max-h-[90vh] w-full max-w-lg flex-col gap-5 overflow-y-auto p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-section-title">New Dubbing</h2>
          <button onClick={onClose} className="text-label" style={{ color: "var(--text-secondary)" }}>
            Close
          </button>
        </div>

        {caps.device === "cpu" && (
          <div
            className="rounded-md px-3 py-2 text-meta"
            style={{ background: "color-mix(in srgb, var(--warn) 12%, transparent)", color: "var(--warn)" }}
          >
            This deployment runs on CPU. Dubbing takes roughly 2 minutes per sentence.
          </div>
        )}

        <div className="flex flex-col gap-2">
          <StepLabel n={1}>Upload file</StepLabel>
          <input
            type="file"
            accept={caps.accepted_formats.join(",")}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="text-body"
          />
          {file && fileTooLarge && (
            <p className="text-meta" style={{ color: "var(--err)" }}>
              This file is larger than the {caps.max_upload_mb}MB limit.
            </p>
          )}
          {file && !formatAccepted && (
            <p className="text-meta" style={{ color: "var(--err)" }}>
              {file.type || "This file type"} isn't accepted. Accepted: {caps.accepted_formats.join(", ")}.
            </p>
          )}
        </div>

        <div className="flex flex-col gap-2">
          <StepLabel n={2}>Language of the source</StepLabel>
          {caps.asr_autodetect ? (
            <>
              <p className="text-meta">This deployment automatically detects the spoken language.</p>
              <label className="flex items-center gap-2 text-label">
                <input
                  type="checkbox"
                  checked={confirmAfterAsr}
                  onChange={(e) => setConfirmAfterAsr(e.target.checked)}
                />
                Ask me to confirm the detected language before continuing
              </label>
            </>
          ) : (
            <p className="text-meta">
              This deployment transcribes a fixed source language; there is nothing to choose here.
            </p>
          )}
        </div>

        <div className="flex flex-col gap-2">
          <StepLabel n={3}>Target languages</StepLabel>
          <LanguageMultiSelect languages={caps.languages} selected={targets} onChange={setTargets} />
          {targets.length > 0 && validTargets.length === 0 && (
            <p className="text-meta" style={{ color: "var(--err)" }}>
              None of the selected languages support dubbing (translate only).
            </p>
          )}
        </div>

        <div className="flex flex-col gap-2">
          <StepLabel n={4}>Options</StepLabel>
          <label className="flex items-center gap-2 text-label">
            <input type="checkbox" checked={preserveEmotion} onChange={(e) => setPreserveEmotion(e.target.checked)} />
            Preserve emotion
          </label>
          <label className="flex items-center gap-2 text-label">
            <input type="checkbox" checked={cloneVoice} onChange={(e) => setCloneVoice(e.target.checked)} />
            Clone the original voice
          </label>
          <label className="flex items-center gap-2 text-label">
            <input type="checkbox" checked={lipSyncAware} onChange={(e) => setLipSyncAware(e.target.checked)} />
            Lip-sync aware timing
          </label>
        </div>

        {error && (
          <p className="text-meta" role="alert" style={{ color: "var(--err)" }}>
            {error}
          </p>
        )}

        <button className="btn-primary" disabled={!canSubmit} onClick={handleSubmit}>
          {submitting ? "Starting…" : "Start Dubbing"}
        </button>
      </div>
    </div>
  );
}
