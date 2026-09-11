/**
 * Panel (b): Detected-language gate. Shown only while the project is
 * awaiting_language_confirmation (app/pipeline/chain.py's gate, added so a
 * wrong auto-detect can be corrected before the expensive stages run --
 * see sur-backend/CONTRACTS.md #3). The override list is
 * caps.source_languages, not caps.languages: those are two different lists
 * on this backend (source = what ASR can transcribe FROM, target = what TTS
 * can dub INTO -- "en" is only ever a source), and using the target list
 * here would silently make English unselectable as a correction.
 */
import { useState } from "react";
import { useReadyCapabilities, sourceLanguageName } from "../lib/capabilities";
import type { ProjectRead } from "../lib/types";

interface DetectedLanguageGateProps {
  project: ProjectRead;
  detectedLanguage: string | null;
  detectedConfidence: number | null;
  onConfirm: (overrideCode?: string) => void;
  onRerunAsr: (overrideCode: string) => void;
  submitting: boolean;
}

export function DetectedLanguageGate({
  project,
  detectedLanguage,
  detectedConfidence,
  onConfirm,
  onRerunAsr,
  submitting,
}: DetectedLanguageGateProps) {
  const caps = useReadyCapabilities();
  const [override, setOverride] = useState<string>(detectedLanguage ?? "");
  const lowConfidence = detectedConfidence != null && detectedConfidence < 0.7;

  if (project.status !== "awaiting_language_confirmation") return null;

  return (
    <div className="panel flex flex-col gap-3 p-5">
      <h3 className="text-section-title">Confirm the source language</h3>
      <div className="flex items-center gap-2">
        <span
          className="rounded-full px-3 py-1 text-label font-medium"
          style={{ background: "var(--bg-hover)" }}
        >
          {detectedLanguage ? sourceLanguageName(caps, detectedLanguage) : "Unknown"}
        </span>
        {detectedConfidence != null && (
          <span className="text-meta font-mono">{Math.round(detectedConfidence * 100)}% confidence</span>
        )}
      </div>

      {lowConfidence && (
        <div
          className="rounded-md px-3 py-2 text-meta"
          style={{ background: "color-mix(in srgb, var(--warn) 12%, transparent)", color: "var(--warn)" }}
        >
          This confidence is low. Check the detected language before continuing.
        </div>
      )}

      <label className="flex flex-col gap-1 text-label">
        Correct it if needed
        <select
          value={override}
          onChange={(e) => setOverride(e.target.value)}
          className="rounded-md px-3 py-2 text-body"
          style={{ border: "1px solid var(--border-strong)" }}
        >
          {caps.source_languages.map((lang) => (
            <option key={lang.code} value={lang.code}>
              {lang.display_name}
            </option>
          ))}
        </select>
      </label>

      <div className="flex gap-3">
        <button className="btn-primary" disabled={submitting} onClick={() => onConfirm(override !== detectedLanguage ? override : undefined)}>
          Continue
        </button>
        <button
          className="btn-secondary"
          disabled={submitting || override === detectedLanguage}
          onClick={() => onRerunAsr(override)}
        >
          Re-run ASR with this language
        </button>
      </div>
    </div>
  );
}
