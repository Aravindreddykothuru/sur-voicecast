// Subscribes to /ws/projects/{id} (app/api/ws.py) and reduces the event
// stream into per-stage progress + a scrolling log, the two things the
// Processing screen renders. Falls back gracefully: if Redis is down the
// backend sends a single "connected" (redis:"offline") message and then
// pings every 20s -- we still show a live connection, just with no stage
// data until the project is polled directly.
import { useEffect, useRef, useState } from "react";
import { API_BASE, USER_EMAIL } from "./api";
import { PIPELINE_STAGE_ORDER, type PipelineStageKey, type ProjectEvent } from "./types";

export interface StageState {
  key: PipelineStageKey;
  done: boolean;
  active: boolean;
  progress: number; // 0..1
  /** Item counts from the backend, so the UI can say "TTS 4/17". Null until
   *  a stage reports them. */
  completed: number | null;
  total: number | null;
  /** Human ETA ("~6m"), derived from observed throughput of this stage.
   *  Synthesis runs ~2 min per sentence on CPU, so a bare spinner is
   *  unusable; this is measured, not guessed from a fixed rate. */
  eta: string | null;
  startedAt: number | null;
}

export interface LogLine {
  ts: number;
  level: "info" | "success" | "warn" | "error";
  message: string;
}

export interface ProjectEventsState {
  connected: boolean;
  /** Whether the last error can ever succeed on retry. */
  errorIsPermanent: boolean;
  stages: StageState[];
  log: LogLine[];
  lastSegmentReady: string | null;
  errorMessage: string | null;
}

function initialStages(): StageState[] {
  return PIPELINE_STAGE_ORDER.map((key) => ({
    key,
    done: false,
    active: false,
    progress: 0,
    completed: null,
    total: null,
    eta: null,
    startedAt: null,
  }));
}

function formatEta(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m}m`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

// Exported for tests: which identity this URL carries is a security
// decision (sending the dev-stub email once logged in identifies the
// wrong user), so it is asserted directly rather than through the hook.
export function wsUrl(projectId: string): string {
  const httpBase = API_BASE.replace(/\/$/, "");
  const wsBase = httpBase.replace(/^http/i, "ws");

  // The server authorizes the subscription before accepting it and closes
  // with 1008 if this identity doesn't own the project. A browser can't set
  // headers on a WebSocket handshake, so identity travels as a query param
  // rather than the Authorization / X-User-Email headers the REST calls use.
  //
  // Prefer the real session token: once logged in, sending the dev-stub
  // email instead would identify the wrong user and get the owner refused
  // their own project's events.
  let token: string | null = null;
  try {
    const raw = localStorage.getItem("sur.auth");
    token = raw ? ((JSON.parse(raw) as { token?: string }).token ?? null) : null;
  } catch {
    token = null;
  }

  const identity = token
    ? `token=${encodeURIComponent(token)}`
    : `user_email=${encodeURIComponent(USER_EMAIL)}`;
  return `${wsBase}/ws/projects/${projectId}?${identity}`;
}



export function useProjectEvents(projectId: string | null): ProjectEventsState {
  const [state, setState] = useState<ProjectEventsState>({
    connected: false,
    errorIsPermanent: false,
    stages: initialStages(),
    log: [],
    lastSegmentReady: null,
    errorMessage: null,
  });

  // Reset when switching projects.
  useEffect(() => {
    setState({
      connected: false,
      errorIsPermanent: false,
      stages: initialStages(),
      log: [],
      lastSegmentReady: null,
      errorMessage: null,
    });
  }, [projectId]);

  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!projectId) return;
    let closedByEffect = false;
    let socket: WebSocket | null = null;

    const connect = () => {
      socket = new WebSocket(wsUrl(projectId));

      socket.onopen = () => setState((s) => ({ ...s, connected: true }));

      socket.onmessage = (ev) => {
        let event: ProjectEvent;
        try {
          event = JSON.parse(ev.data);
        } catch {
          return;
        }
        setState((s) => applyEvent(s, event));
      };

      socket.onclose = () => {
        setState((s) => ({ ...s, connected: false }));
        if (!closedByEffect) {
          reconnectRef.current = setTimeout(connect, 3000);
        }
      };

      socket.onerror = () => socket?.close();
    };

    connect();

    return () => {
      closedByEffect = true;
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      socket?.close();
    };
  }, [projectId]);

  return state;
}

function fmtTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString("en-GB", { hour12: false });
}

function applyEvent(s: ProjectEventsState, event: ProjectEvent): ProjectEventsState {
  switch (event.type) {
    case "connected":
      return { ...s, connected: true };
    case "ping":
      return s;
    case "stage_started": {
      const stages = s.stages.map((st) =>
        st.key === event.stage
          ? { ...st, active: true, done: false, progress: 0, completed: null, total: null, eta: null, startedAt: event.ts }
          : st,
      );
      return {
        ...s,
        stages,
        log: [...s.log, { ts: event.ts, level: "info", message: `Stage started: ${event.stage}` }],
      };
    }
    case "stage_progress": {
      const stages = s.stages.map((st) => {
        if (st.key !== event.stage) return st;
        const startedAt = st.startedAt ?? event.ts;
        // ETA from this stage's own observed rate rather than a fixed
        // assumption -- CPU vs GPU differ by an order of magnitude.
        let eta: string | null = null;
        const elapsed = event.ts - startedAt;
        if (elapsed > 2 && event.progress > 0.02 && event.progress < 1) {
          eta = formatEta(elapsed * (1 - event.progress) / event.progress) || null;
        }
        return {
          ...st,
          active: true,
          progress: event.progress,
          completed: event.completed ?? st.completed,
          total: event.total ?? st.total,
          startedAt,
          eta,
        };
      });
      const message = event.detail
        ? `${event.stage}: ${event.detail} (${Math.round(event.progress * 100)}%)`
        : `${event.stage}: ${Math.round(event.progress * 100)}%`;
      return { ...s, stages, log: [...s.log, { ts: event.ts, level: "info", message }] };
    }
    case "stage_completed": {
      const stages = s.stages.map((st) =>
        st.key === event.stage ? { ...st, active: false, done: true, progress: 1, eta: null } : st,
      );
      return {
        ...s,
        stages,
        log: [...s.log, { ts: event.ts, level: "success", message: `Stage completed: ${event.stage}` }],
      };
    }
    case "segment_ready":
      return {
        ...s,
        lastSegmentReady: event.segment_id,
        log: [...s.log, { ts: event.ts, level: "success", message: `Segment ready: ${event.segment_id}` }],
      };
    case "error":
      return {
        ...s,
        errorMessage: event.message,
        errorIsPermanent: event.permanent ?? false,
        log: [...s.log, { ts: event.ts, level: "error", message: `[${event.stage}] ${event.message}` }],
      };
    default:
      return s;
  }
}

export { fmtTime };
