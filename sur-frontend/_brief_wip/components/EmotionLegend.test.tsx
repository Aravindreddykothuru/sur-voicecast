import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { CapabilitiesProvider, useCapabilities } from "../lib/capabilities";
import { EmotionLegend } from "./EmotionLegend";
import type { Capabilities } from "../lib/types";
import type { ReactNode } from "react";

// Mirrors App.tsx's CapabilitiesGate: real usage never mounts a component
// that calls useReadyCapabilities() before capabilities have loaded.
function TestGate({ children }: { children: ReactNode }) {
  const { caps, loading } = useCapabilities();
  if (loading || !caps) return null;
  return <>{children}</>;
}

const FOUR_WAY: Capabilities = {
  languages: [],
  source_languages: [],
  emotions: [
    { label: "neutral", index: 0, color: "#8898c8" },
    { label: "happiness", index: 1, color: "#34d399" },
    { label: "anger", index: 2, color: "#f87171" },
    { label: "sadness", index: 3, color: "#818cf8" },
  ],
  providers: {},
  emotion_confidence_floor: 0.4,
  asr_autodetect: true,
  device: "cpu",
  max_upload_mb: 2048,
  accepted_formats: ["video/mp4"],
};

beforeEach(() => vi.unstubAllGlobals());

describe("EmotionLegend (production component)", () => {
  it("renders exactly the backend's emotions plus uncertain -- never fear/surprise for a model that predicts neither", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => FOUR_WAY }) as Response));

    render(
      <CapabilitiesProvider>
        <TestGate>
          <EmotionLegend />
        </TestGate>
      </CapabilitiesProvider>,
    );

    await waitFor(() => expect(screen.getByText("neutral")).toBeInTheDocument());
    for (const label of FOUR_WAY.emotions.map((e) => e.label)) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByText("uncertain")).toBeInTheDocument();

    for (const absent of ["fear", "surprise"]) {
      expect(screen.queryByText(absent)).toBeNull();
    }
  });
});
