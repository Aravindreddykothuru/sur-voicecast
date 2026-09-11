// Real signup/login against sur-backend's /api/auth/{signup,login} (see
// sur-backend/app/api/routes_auth.py). The token this returns is attached
// as `Authorization: Bearer` by api.ts's request() -- api.ts's request()
// prefers it over the old X-User-Email dev header the moment it exists, so
// logging in actually changes which account every subsequent call acts as.
import { API_BASE, ApiError } from "./api";

export interface AuthUser {
  id: string;
  email: string;
  name: string | null;
}

export interface StoredAuth {
  token: string;
  user: AuthUser;
}

const STORAGE_KEY = "sur.auth";

export function getStoredAuth(): StoredAuth | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as StoredAuth) : null;
  } catch {
    return null;
  }
}

function setStoredAuth(auth: StoredAuth): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(auth));
  } catch {
    /* private browsing / storage disabled -- the session still works for
       this tab via the in-memory token api.ts holds, just won't persist. */
  }
}

export function logout(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

async function authRequest(path: "/api/auth/signup" | "/api/auth/login", body: unknown): Promise<StoredAuth> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  let payload: Record<string, unknown> = {};
  try {
    payload = await res.json();
  } catch {
    /* non-JSON body */
  }
  if (!res.ok) {
    // FastAPI's 422 validation errors come back as {detail: [{msg, ...}]},
    // not a plain string -- surface the first message rather than "[object
    // Object]" so an empty/malformed field shows something readable.
    const raw = payload.detail;
    const message = Array.isArray(raw) ? (raw[0]?.msg ?? "Invalid request.") : typeof raw === "string" ? raw : res.statusText;
    throw new ApiError(res.status, message);
  }
  const auth = payload as unknown as StoredAuth;
  setStoredAuth(auth);
  return auth;
}

export function signup(email: string, password: string, name?: string): Promise<StoredAuth> {
  return authRequest("/api/auth/signup", { email, password, name: name || undefined });
}

export function login(email: string, password: string): Promise<StoredAuth> {
  return authRequest("/api/auth/login", { email, password });
}
