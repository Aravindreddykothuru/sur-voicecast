/**
 * The UI must never assert a capability the backend didn't report.
 *
 * These are the tests that would have caught the shipped bugs: a picker
 * offering 12 languages against a backend that supported 7 (the other 5
 * crashed the job), and six emotion buttons against a four-label model.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CapabilitiesProvider, emotionDisplay, useCapabilities } from "./capabilities";
import type { Capabilities } from "./types";

// One narrow backend: fewer languages than the UI ever hardcoded, one of them
// translate-only, and only the four emotions the real model predicts.
const NARROW: Capabilities = {
  languages: [
    { code: "hi", display_name: "Hindi", flores_code: "hin_Deva", tts_available: true },
    { code: "te", display_name: "Telugu", flores_code: "tel_Telu", tts_available: true },
    { code: "kok", display_name: "Konkani", flores_code: "gom_Deva", tts_available: false },
  ],
  source_languages: [
    { code: "en", display_name: "English" },
    { code: "hi", display_name: "Hindi" },
    { code: "te", display_name: "Telugu" },
  ],
  emotions: [
    { label: "neutral", index: 0, color: "#8898c8" },
    { label: "happiness", index: 1, color: "#34d399" },
    { label: "anger", index: 2, color: "#f87171" },
    { label: "sadness", index: 3, color: "#818cf8" },
  ],
  providers: { asr: "real", diarization: "real", translation: "real", emotion: "real", tts: "real" },
  emotion_confidence_floor: 0.4,
  asr_autodetect: true,
  device: "cpu",
  max_upload_mb: 2048,
  accepted_formats: ["video/mp4"],
};

function mockCapabilities(body: unknown, ok = true) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      ok
        ? ({ ok: true, status: 200, json: async () => body } as Response)
        : ({ ok: false, status: 503, statusText: "Service Unavailable", json: async () => ({ detail: "backend down" }) } as Response),
    ),
  );
}

/** Minimal stand-in for the real language selector: same contract (render only
 *  what capabilities returned, disable non-dubbing options, block on error). */
function LanguageSelector() {
  const { caps, loading, error } = useCapabilities();
  if (loading) return <p>Loading…</p>;
  if (error || !caps) {
    return (
      <div>
        <p role="alert">{error}</p>
        <button disabled>Start Processing</button>
      </div>
    );
  }
  return (
    <div>
      <select aria-label="Target Language">
        {caps.languages.map((l) => (
          <option key={l.code} value={l.code} disabled={!l.tts_available}>
            {l.display_name}
            {l.tts_available ? "" : " (translate only)"}
          </option>
        ))}
      </select>
      <button>Start Processing</button>
    </div>
  );
}

function EmotionButtons() {
  const { caps } = useCapabilities();
  if (!caps) return null;
  return (
    <div>
      {caps.emotions.map((e) => (
        <button key={e.label}>{e.label}</button>
      ))}
    </div>
  );
}

beforeEach(() => vi.unstubAllGlobals());

describe("language selector", () => {
  it("renders only the languages the backend returned, and nothing else", async () => {
    mockCapabilities(NARROW);
    render(
      <CapabilitiesProvider>
        <LanguageSelector />
      </CapabilitiesProvider>,
    );

    const select = await screen.findByLabelText("Target Language");
    const options = Array.from(select.querySelectorAll("option"));
    const rendered = options.map((o) => o.getAttribute("value"));

    expect(rendered).toEqual(["hi", "te", "kok"]);

    // The exact regression: languages the UI used to hardcode must not appear
    // when the backend didn't return them.
    for (const absent of ["ta", "kn", "ml", "bn", "mr", "gu", "pa", "or", "as", "ur"]) {
      expect(rendered).not.toContain(absent);
    }
    expect(options).toHaveLength(NARROW.languages.length);
  });

  it("marks a translate-only language and disables it for dubbing", async () => {
    mockCapabilities(NARROW);
    render(
      <CapabilitiesProvider>
        <LanguageSelector />
      </CapabilitiesProvider>,
    );

    const konkani = await screen.findByRole("option", { name: /Konkani/ });
    expect(konkani).toBeDisabled();
    expect(konkani.textContent).toMatch(/translate only/i);

    expect(await screen.findByRole("option", { name: "Hindi" })).not.toBeDisabled();
  });
});

describe("capabilities failure", () => {
  it("shows the error and disables submit instead of guessing a default list", async () => {
    mockCapabilities(null, false);
    render(
      <CapabilitiesProvider>
        <LanguageSelector />
      </CapabilitiesProvider>,
    );

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBeTruthy();
    expect(screen.getByRole("button", { name: "Start Processing" })).toBeDisabled();

    // Crucially: no language options at all. A fallback list here is the bug.
    expect(screen.queryByLabelText("Target Language")).toBeNull();
  });

  it("exposes NO capabilities at all on failure -- not even a partial set", async () => {
    // Asserted on the provider itself, not through a component: a fallback
    // implementation that also cleared `error` would slip past any test that
    // only checks how a component renders. The invariant is that the provider
    // never synthesises capabilities the backend didn't send.
    mockCapabilities(null, false);
    let seen: ReturnType<typeof useCapabilities> | null = null;
    function Probe() {
      seen = useCapabilities();
      return null;
    }
    render(
      <CapabilitiesProvider>
        <Probe />
      </CapabilitiesProvider>,
    );

    await waitFor(() => expect(seen?.loading).toBe(false));
    expect(seen!.caps).toBeNull();
    expect(seen!.error).toBeTruthy();
  });
});

describe("emotion display", () => {
  it("never renders a label the backend didn't return", async () => {
    mockCapabilities(NARROW);
    render(
      <CapabilitiesProvider>
        <EmotionButtons />
      </CapabilitiesProvider>,
    );

    await waitFor(() => expect(screen.getByRole("button", { name: "neutral" })).toBeInTheDocument());

    for (const label of NARROW.emotions.map((e) => e.label)) {
      expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
    }
    // The model predicts four labels; these two must appear nowhere.
    for (const absent of ["fear", "surprise", "Fear", "Surprise"]) {
      expect(screen.queryByText(absent)).toBeNull();
    }
    expect(screen.getAllByRole("button")).toHaveLength(NARROW.emotions.length);
  });

  it("renders a below-floor prediction as uncertain rather than as fact", () => {
    const low = emotionDisplay(NARROW, "anger", 0.31);
    expect(low.uncertain).toBe(true);
    expect(low.text).toBe("uncertain");
    expect(low.text).not.toBe("anger");

    const confident = emotionDisplay(NARROW, "anger", 0.82);
    expect(confident.uncertain).toBe(false);
    expect(confident.text).toBe("anger");
    // Color is assigned by the emotion's own index (src/lib/theme.ts), never
    // hardcoded per label -- confirm the index round-trips, not a color.
    expect(confident.index).toBe(NARROW.emotions.find((e) => e.label === "anger")!.index);
  });

  it("treats an unknown label as unrenderable rather than inventing styling", () => {
    const unknown = emotionDisplay(NARROW, "fear", 0.99);
    expect(unknown.uncertain).toBe(true);
    expect(unknown.text).not.toBe("fear");
    expect(unknown.index).toBeNull();
  });

  it("treats a missing score as uncertain, never as confident", () => {
    expect(emotionDisplay(NARROW, "anger", null).uncertain).toBe(true);
  });
});
