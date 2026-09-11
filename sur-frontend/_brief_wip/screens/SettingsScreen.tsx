/**
 * Screen 5: Settings. AppShell's sidebar spec calls for exactly 4 nav items
 * (Projects, New Dubbing, Runtime, Settings), but only four content screens
 * are otherwise specified. Rather than invent a settings feature this app
 * doesn't have (no accounts, no billing, no preferences persisted
 * anywhere), this shows the two things that are real and actually useful
 * to see: which backend this app is talking to, and the stubbed dev
 * identity every request is sent as (app/core/security.py's
 * X-User-Email header -- there is no real auth yet).
 */
import { API_BASE } from "../lib/api";

const USER_EMAIL = import.meta.env.VITE_DEV_USER_EMAIL ?? "dev@sur.local";

export function SettingsScreen() {
  return (
    <div className="panel flex flex-col gap-4 p-5">
      <h3 className="text-section-title">Settings</h3>
      <div className="flex flex-col gap-1">
        <span className="text-label">Backend</span>
        <span className="text-body font-mono">{API_BASE}</span>
      </div>
      <div className="flex flex-col gap-1">
        <span className="text-label">Signed in as</span>
        <span className="text-body font-mono">{USER_EMAIL}</span>
        <span className="text-meta">Stubbed auth (X-User-Email header) -- there is no account system yet.</span>
      </div>
    </div>
  );
}
