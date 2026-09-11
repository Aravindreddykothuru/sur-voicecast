/**
 * The regression this guards against: mux_timeline() places every clip at
 * its own source timecode, but if a synthesized clip's own duration
 * (tts_duration_ms) is longer or shorter than the slot the source segment
 * occupied, it still overruns into -- or leaves a gap before -- the next
 * clip. That's real, visible desync even though every clip's start_ms is
 * "correct." This must be flagged, not silently rendered as if the timeline
 * were clean.
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { CapabilitiesProvider, useCapabilities } from "../lib/capabilities";
import { SyncTimeline, segmentDriftMs, DRIFT_THRESHOLD_MS } from "./SyncTimeline";
import type { Capabilities } from "../lib/types";
import type { SegmentRead } from "../lib/types";
import type { ReactNode } from "react";
import { vi, beforeEach } from "vitest";

// Mirrors App.tsx's CapabilitiesGate: real usage never mounts a component
// that calls useReadyCapabilities() before capabilities have loaded.
function TestGate({ children }: { children: ReactNode }) {
  const { caps, loading } = useCapabilities();
  if (loading || !caps) return null;
  return <>{children}</>;
}

const CAPS: Capabilities = {
  languages: [{ code: "te", display_name: "Telugu", flores_code: "tel_Telu", tts_available: true }],
  source_languages: [{ code: "en", display_name: "English" }],
  emotions: [{ label: "neutral", index: 0, color: "#8898c8" }],
  providers: { asr: "mock", diarization: "mock", translation: "mock", emotion: "mock", tts: "mock" },
  emotion_confidence_floor: 0.4,
  asr_autodetect: true,
  device: "cpu",
  max_upload_mb: 2048,
  accepted_formats: ["video/mp4"],
};

function seg(overrides: Partial<SegmentRead>): SegmentRead {
  return {
    id: "s1",
    project_id: "p1",
    speaker_id: null,
    index: 0,
    start_ms: 0,
    end_ms: 4000,
    source_text: "hello",
    detected_language: "en",
    detected_language_confidence: 0.95,
    translated_text: "hola",
    emotion_label: "neutral",
    emotion_score: 0.9,
    emotion_overridden: false,
    source_audio_url: null,
    tts_audio_url: null,
    tts_duration_ms: 4000,
    sync_offset_pct: null,
    status: "muxed",
    error_message: null,
    error_is_permanent: null,
    source_language: "en",
    review_language: true,
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-01-01T00:00:00Z",
    ...overrides,
  };
}

beforeEach(() => vi.unstubAllGlobals());

describe("segmentDriftMs", () => {
  it("is zero when the synthesized clip fits its slot exactly", () => {
    expect(segmentDriftMs(seg({ start_ms: 0, end_ms: 4000, tts_duration_ms: 4000 }))).toBe(0);
  });

  it("measures how far a synthesized clip overruns its slot", () => {
    // Slot is 4000ms - 0ms = 4000ms; the clip rendered 4500ms of audio.
    expect(segmentDriftMs(seg({ start_ms: 0, end_ms: 4000, tts_duration_ms: 4500 }))).toBe(500);
  });

  it("measures underrun the same way as overrun", () => {
    expect(segmentDriftMs(seg({ start_ms: 0, end_ms: 4000, tts_duration_ms: 3200 }))).toBe(800);
  });
});

function mockCapabilities() {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => CAPS }) as Response));
}

describe("SyncTimeline drift warning", () => {
  it("flags drift when a dubbed clip misses its source timecode by more than the threshold", async () => {
    mockCapabilities();
    const drifted = seg({ id: "s1", start_ms: 0, end_ms: 4000, tts_duration_ms: 4000 + DRIFT_THRESHOLD_MS + 50 });
    render(
      <CapabilitiesProvider>
        <TestGate>
          <SyncTimeline segments={[drifted]} />
        </TestGate>
      </CapabilitiesProvider>,
    );

    const warning = await screen.findByText(/clips are not landing on their timecodes/i);
    expect(warning).toBeInTheDocument();
  });

  it("does not flag drift within the threshold", async () => {
    mockCapabilities();
    const onTime = seg({ id: "s1", start_ms: 0, end_ms: 4000, tts_duration_ms: 4000 + DRIFT_THRESHOLD_MS - 50 });
    render(
      <CapabilitiesProvider>
        <TestGate>
          <SyncTimeline segments={[onTime]} />
        </TestGate>
      </CapabilitiesProvider>,
    );

    // Let the capabilities fetch resolve before asserting an absence.
    await screen.findByText("Sync timeline");
    expect(screen.queryByText(/clips are not landing on their timecodes/i)).toBeNull();
  });
});
