/**
 * Panel (c): Sync timeline. Two tracks (source segments / dubbed clips),
 * blocks positioned by real timing fields, colored by emotion index (grey
 * "uncertain" below emotion_confidence_floor). Max drift is measured, not
 * guessed: for each segment it's how far the synthesized clip's own
 * duration (tts_duration_ms) deviates from the slot the source segment
 * occupied (end_ms - start_ms). A clip that renders longer than its slot
 * visibly overruns into the next block on the Dubbed track, which is the
 * real, visible version of "this clip is not landing on its timecode."
 *
 * "Click-to-seek" plays that block's own audio (source_audio_url /
 * tts_audio_url, both real per-segment fields) rather than driving a
 * combined video player -- there is no single "get the muxed preview video"
 * endpoint wired into ProjectRead/SegmentRead to seek within, only the
 * final export (GET /api/projects/{id}/export) and each segment's own clip.
 */
import { useRef, useState } from "react";
import { resolveUrl } from "../lib/api";
import { emotionDisplay, useReadyCapabilities } from "../lib/capabilities";
import { emotionColor, UNCERTAIN_COLOR } from "../lib/theme";
import type { SegmentRead } from "../lib/types";
import { EmotionLegend } from "./EmotionLegend";

const DRIFT_THRESHOLD_MS = 200;

function segmentDriftMs(seg: SegmentRead): number {
  if (seg.tts_duration_ms == null) return 0;
  const slot = seg.end_ms - seg.start_ms;
  return Math.abs(seg.tts_duration_ms - slot);
}

function TrackRow({
  label,
  segments,
  totalMs,
  getStart,
  getWidth,
  audioField,
  onPlay,
}: {
  label: string;
  segments: SegmentRead[];
  totalMs: number;
  getStart: (s: SegmentRead) => number;
  getWidth: (s: SegmentRead) => number;
  audioField: "source_audio_url" | "tts_audio_url";
  onPlay: (url: string) => void;
}) {
  const caps = useReadyCapabilities();

  return (
    <div className="flex flex-col gap-1">
      <span className="text-meta">{label}</span>
      <div className="relative h-9 rounded-md" style={{ background: "var(--bg-panel-muted)" }}>
        {segments.map((seg) => {
          const left = totalMs > 0 ? (getStart(seg) / totalMs) * 100 : 0;
          const width = totalMs > 0 ? Math.max((getWidth(seg) / totalMs) * 100, 0.5) : 0;
          const display = emotionDisplay(caps, seg.emotion_label, seg.emotion_score);
          const color = display.uncertain ? UNCERTAIN_COLOR : emotionColor(display.index ?? 0);
          const url = seg[audioField];
          return (
            <button
              key={seg.id}
              disabled={!url}
              onClick={() => url && onPlay(url)}
              title={`${seg.source_text ?? ""} (${Math.round(getStart(seg))}ms)`}
              className="absolute top-1 h-7 rounded"
              style={{ left: `${left}%`, width: `${width}%`, background: color, cursor: url ? "pointer" : "default" }}
            />
          );
        })}
      </div>
    </div>
  );
}

export function SyncTimeline({ segments }: { segments: SegmentRead[] }) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [nowPlaying, setNowPlaying] = useState<string | null>(null);

  const totalMs = segments.reduce((max, s) => Math.max(max, s.start_ms + (s.tts_duration_ms ?? s.end_ms - s.start_ms), s.end_ms), 0);
  const maxDrift = segments.reduce((max, s) => Math.max(max, segmentDriftMs(s)), 0);
  const drifted = maxDrift > DRIFT_THRESHOLD_MS;

  function play(url: string) {
    const resolved = resolveUrl(url);
    setNowPlaying(resolved);
    if (audioRef.current) {
      audioRef.current.src = resolved;
      audioRef.current.play().catch(() => {});
    }
  }

  return (
    <div className="panel flex flex-col gap-3 p-5">
      <div className="flex items-center justify-between">
        <h3 className="text-section-title">Sync timeline</h3>
        {drifted && (
          <span className="text-meta font-medium" style={{ color: "var(--err)" }}>
            Max drift {Math.round(maxDrift)}ms — clips are not landing on their timecodes
          </span>
        )}
      </div>

      {segments.length === 0 ? (
        <p className="text-meta">No segments yet.</p>
      ) : (
        <>
          <TrackRow
            label="Source segments"
            segments={segments}
            totalMs={totalMs}
            getStart={(s) => s.start_ms}
            getWidth={(s) => s.end_ms - s.start_ms}
            audioField="source_audio_url"
            onPlay={play}
          />
          <TrackRow
            label="Dubbed clips"
            segments={segments}
            totalMs={totalMs}
            getStart={(s) => s.start_ms}
            getWidth={(s) => s.tts_duration_ms ?? s.end_ms - s.start_ms}
            audioField="tts_audio_url"
            onPlay={play}
          />
          <audio ref={audioRef} hidden />
          {nowPlaying && <p className="text-meta">Playing…</p>}
          <EmotionLegend />
        </>
      )}
    </div>
  );
}

export { segmentDriftMs, DRIFT_THRESHOLD_MS };
