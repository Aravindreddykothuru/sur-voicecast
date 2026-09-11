/**
 * Capabilities context -- the only place the UI learns what it may offer.
 *
 * Rule: the frontend knows nothing the backend didn't tell it. No hardcoded
 * language lists, no hardcoded emotion labels, no fallback defaults. If this
 * fetch fails the app blocks with an error rather than guessing, because
 * guessing is what shipped a picker with 5 languages that killed the job.
 * See sur-backend/CONTRACTS.md #2.
 */
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { getCapabilities } from "./api";
import type { Capabilities, CapabilityEmotion, EmotionLabel } from "./types";

// A minimal useQuery-shaped result -- {data, isLoading, isError, error,
// refetch} -- without pulling in a data-fetching library. One query, one
// consumer (CapabilitiesProvider); a second use case would justify the
// dependency, this one doesn't.
interface QueryResult<T> {
  data: T | null;
  isLoading: boolean;
  isError: boolean;
  error: string | null;
  refetch: () => void;
}

function useQuery<T>(queryFn: () => Promise<T>, deps: unknown[]): QueryResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(() => {
    setIsLoading(true);
    setError(null);
    queryFn()
      .then((result) => {
        setData(result);
        setError(null);
      })
      .catch((e: unknown) => {
        setData(null);
        setError(e instanceof Error ? e.message : "Request failed");
      })
      .finally(() => setIsLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(run, [run]);

  return { data, isLoading, isError: !!error, error, refetch: run };
}

interface CapabilitiesState {
  caps: Capabilities | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

const Ctx = createContext<CapabilitiesState | null>(null);

export function CapabilitiesProvider({ children }: { children: ReactNode }) {
  const query = useQuery(getCapabilities, []);

  const state: CapabilitiesState = {
    caps: query.data,
    loading: query.isLoading,
    error: query.error,
    reload: query.refetch,
  };

  return <Ctx.Provider value={state}>{children}</Ctx.Provider>;
}

/** Throws if used outside the provider -- a component that needs capabilities
 *  must not silently render an empty picker. */
export function useCapabilities(): CapabilitiesState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useCapabilities must be used inside <CapabilitiesProvider>");
  return ctx;
}

/** Capabilities, guaranteed loaded. Only call below a <CapabilitiesGate>. */
export function useReadyCapabilities(): Capabilities {
  const { caps } = useCapabilities();
  if (!caps) throw new Error("capabilities not loaded; render inside <CapabilitiesGate>");
  return caps;
}

// ── Derived lookups (no hardcoded tables) ───────────────────────────────
export function emotionIndexOf(caps: Capabilities, label: string | null | undefined): number | null {
  if (!label) return null;
  const found = caps.emotions.find((e) => e.label === label);
  return found ? found.index : null;
}

export function isKnownEmotion(caps: Capabilities, label: string | null | undefined): boolean {
  return !!label && caps.emotions.some((e) => e.label === label);
}

/** A prediction the UI may state as fact, or one it must hedge.
 *  Never present a low-confidence guess as a label. */
export function emotionDisplay(
  caps: Capabilities,
  label: string | null | undefined,
  score: number | null | undefined,
): { text: string; index: number | null; uncertain: boolean } {
  if (!isKnownEmotion(caps, label)) return { text: "—", index: null, uncertain: true };
  if (score == null || score < caps.emotion_confidence_floor) {
    return { text: "uncertain", index: emotionIndexOf(caps, label), uncertain: true };
  }
  return { text: label as string, index: emotionIndexOf(caps, label), uncertain: false };
}

export function languageName(caps: Capabilities, code: string): string {
  return caps.languages.find((l) => l.code === code)?.display_name ?? code;
}

export function sourceLanguageName(caps: Capabilities, code: string): string {
  return caps.source_languages.find((l) => l.code === code)?.display_name ?? code;
}

export function isSelectableForDubbing(e: CapabilityEmotion | undefined): boolean {
  return !!e;
}

export type { EmotionLabel };
