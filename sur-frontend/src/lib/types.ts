// Mirrors sur-backend's Pydantic schemas (app/schemas/*.py) and model enums
// (app/models/*.py). Keep in sync with the backend by hand -- there's no
// OpenAPI codegen wired up yet, so this is the contract until there is one.

export type ProjectStatus =
  | "draft"
  | "uploading"
  | "queued"
  | "processing"
  /** Parked after ASR: the detected source language needs confirming before
   *  the expensive stages run. */
  | "awaiting_language_confirmation"
  | "ready"
  | "failed";

export interface ProjectRead {
  id: string;
  title: string;
  target_languages: string[];
  status: ProjectStatus;
  current_stage: string | null;
  preserve_emotion: boolean;
  clone_voice: boolean;
  lip_sync_aware: boolean;
  tts_model: string | null;
  error_message: string | null;
  /** True when retrying cannot help (bad input, missing row). The UI must not
   *  say "Retrying…" for these. */
  error_is_permanent: boolean | null;
  source_language: string | null;
  review_language: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProjectListItem extends ProjectRead {
  source_video_duration_ms: number | null;
  segment_count: number;
}

/** Structured view of a project's error, composed from the three real
 *  fields the backend already returns (error_message, error_is_permanent,
 *  current_stage -- _mark_project_failed sets current_stage to the failing
 *  stage before it commits). Not a client-side guess: every field it reads
 *  comes straight from ProjectRead, just reshaped for ErrorPanel. A backend
 *  that nested these itself (project.error: {kind, message, stage}) would
 *  be cleaner; until it does, this is composition, not invention. */
export interface ProjectError {
  kind: "permanent" | "transient";
  message: string;
  stage: string | null;
}

export function projectError(project: ProjectRead): ProjectError | null {
  if (project.status !== "failed" || !project.error_message) return null;
  return {
    kind: project.error_is_permanent ? "permanent" : "transient",
    message: project.error_message,
    stage: project.current_stage,
  };
}

export interface UploadUrlResponse {
  source_video_id: string;
  upload_url: string;
  storage_key: string;
  method: string;
  expires_in: number;
}

// An emotion label is whatever the backend reports. Deliberately NOT a union
// of fixed literals: the valid set is decided at runtime by the loaded
// model's config.id2label and served via /api/capabilities. Pinning a fixed
// set here is how the UI came to render labels the model never predicts.
export type EmotionLabel = string;

export type SegmentStatus =
  | "pending"
  | "transcribed"
  | "emotion_detected"
  | "translated"
  | "synthesized"
  | "muxed"
  | "failed";

export interface SegmentRead {
  id: string;
  project_id: string;
  speaker_id: string | null;
  index: number;
  start_ms: number;
  end_ms: number;
  source_text: string | null;
  detected_language: string | null;
  detected_language_confidence: number | null;
  translated_text: string | null;
  emotion_label: EmotionLabel | null;
  emotion_score: number | null;
  emotion_overridden: boolean;
  source_audio_url: string | null;
  tts_audio_url: string | null;
  tts_duration_ms: number | null;
  sync_offset_pct: number | null;
  status: SegmentStatus;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export type ExportStatus = "pending" | "running" | "ready" | "failed";

export interface SegmentQaEntry {
  segment_id: string;
  wer?: number;
  sync_offset_pct?: number;
  speaker_similarity?: number;
}

export interface QaReport {
  segments?: SegmentQaEntry[];
  overall?: Record<string, number | string>;
}

export interface ExportRead {
  id: string;
  project_id: string;
  status: ExportStatus;
  format: string;
  resolution: string;
  output_url: string | null;
  qa_report: QaReport | null;
  created_at: string;
  completed_at: string | null;
}

// Pipeline stage keys as emitted by app/pipeline/tasks.py, in run order.
export const PIPELINE_STAGE_ORDER = [
  "extract_audio",
  "chunk_and_diarize",
  "transcribe",
  "detect_emotion",
  "translate",
  "synthesize",
  "mux_export",
] as const;
export type PipelineStageKey = (typeof PIPELINE_STAGE_ORDER)[number];

export const PIPELINE_STAGE_LABELS: Record<PipelineStageKey, string> = {
  extract_audio: "Audio Extraction",
  chunk_and_diarize: "Chunking & Diarization",
  transcribe: "Speech Recognition",
  detect_emotion: "Emotion Detection",
  translate: "Translation",
  synthesize: "Voice Synthesis",
  mux_export: "Mux & Export",
};

// Events published on the project's Redis channel (app/pipeline/events.py)
// and forwarded verbatim over /ws/projects/{id} (app/api/ws.py).
export type ProjectEvent =
  | { type: "stage_started"; stage: string; ts: number }
  | {
      type: "stage_progress";
      stage: string;
      progress: number;
      detail: string | null;
      /** e.g. 4 and 17 so the UI can say "TTS 4/17" rather than a bare %. */
      completed: number | null;
      total: number | null;
      ts: number;
    }
  | { type: "stage_completed"; stage: string; ts: number }
  | { type: "segment_ready"; segment_id: string; ts: number }
  | { type: "error"; stage: string; message: string; permanent: boolean; ts: number }
  | { type: "connected"; status: string; redis: string }
  | { type: "ping" };

// ── Capabilities (GET /api/capabilities) ────────────────────────────────
// The backend is the single source of truth for what can be offered. The UI
// must not carry its own copy of these lists: a frontend list of 12 target
// languages against a backend that supported 7 is exactly how 5 of them
// reached users and then failed the job; six emotion buttons against a
// four-label model is the same mistake. See sur-backend/CONTRACTS.md #2.
export interface CapabilityLanguage {
  code: string;
  display_name: string;
  flores_code: string;
  tts_available: boolean;
}

// What this engine can transcribe+correctly-translate FROM. Deliberately a
// separate type from CapabilityLanguage (dub-INTO targets): the two lists
// differ ("en" is a valid source but never a dub target) and conflating them
// is exactly how a wrong auto-detect used to get silently translated as if
// it were English. See sur-backend/CONTRACTS.md #2 and #3.
export interface CapabilitySourceLanguage {
  code: string;
  display_name: string;
}

export interface CapabilityEmotion {
  label: EmotionLabel;
  /** Position in the array the backend returned, NOT a hardcoded ordinal.
   *  Colors are assigned by index (src/lib/theme.ts's emotionColor), never
   *  by matching the label string, so a model swap that renames or reorders
   *  labels can't silently point at the wrong color. */
  index: number;
  color: string;
}

export interface Capabilities {
  languages: CapabilityLanguage[];
  source_languages: CapabilitySourceLanguage[];
  emotions: CapabilityEmotion[];
  providers: Record<string, string>;
  /** Below this confidence the UI must render "uncertain", not the label. */
  emotion_confidence_floor: number;
  /** Whether ASR_LANGUAGE=auto -- gates the "Autodetect" source-language
   *  option. False means this deployment pins a fixed ASR language. */
  asr_autodetect: boolean;
  /** Conservative single summary of where real providers actually run.
   *  Never "cuda" unless every GPU-relevant stage is configured for it. */
  device: "cpu" | "cuda";
  max_upload_mb: number;
  accepted_formats: string[];
}

