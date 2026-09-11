import { useState, useEffect, useRef } from "react";
import robotImg from "@/imports/image-23.png";
import { login, signup } from "@/lib/auth";
import { ApiError } from "@/lib/api";

const NAV_LINKS: { label: string; href: string }[] = [];

const CSS = `
/* ── VOICECAST Landing ─────────────────────────────── */
.ec-hero {
  position: relative;
  width: 100%;
  height: 100vh;
  height: 100svh;
  min-height: 560px;
  overflow: hidden;
  display: grid;
  grid-template-rows: auto 1fr;
  isolation: isolate;
  background: #000;
  --ease-premium: cubic-bezier(0.16, 1, 0.3, 1);
  --gutter: clamp(20px, 5vw, 100px);
  --line: rgba(255,255,255,0.14);
  --line-strong: rgba(255,255,255,0.26);
  --text-dim: rgba(255,255,255,0.62);
  --text-dimmer: rgba(255,255,255,0.42);
  --fill-ghost: rgba(255,255,255,0.05);
  --fill-solid: rgba(255,255,255,0.10);
  --font-display: "Sora", "Helvetica Neue", Helvetica, Arial, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, "SF Mono", Menlo, Consolas, monospace;
}
@media (max-height: 640px) {
  .ec-hero { min-height: 100svh; }
}



/* Scrim — sits ABOVE the image so it actually darkens it for text contrast */
.ec-scrim {
  position: absolute;
  inset: 0;
  z-index: 2;
  pointer-events: none;
  background:
    linear-gradient(to right, transparent 28%, rgba(0,0,0,0.5) 64%, rgba(0,0,0,0.86) 100%),
    linear-gradient(to bottom, rgba(0,0,0,0.55) 0%, transparent 24%, transparent 76%, rgba(0,0,0,0.72) 100%);
}
@media (max-width: 720px) {
  .ec-scrim {
    background: linear-gradient(to bottom, rgba(0,0,0,0.72) 0%, rgba(0,0,0,0.35) 32%, rgba(0,0,0,0.85) 100%);
  }
}

/* Nav */
.ec-nav {
  position: relative;
  z-index: 60;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 32px;
  padding: clamp(20px, 2.4vw, 34px) var(--gutter);
  padding-left: max(var(--gutter), env(safe-area-inset-left, 0px));
  padding-right: max(var(--gutter), env(safe-area-inset-right, 0px));
}
.ec-logo {
  font-family: var(--font-display);
  font-weight: 200;
  font-size: clamp(20px, 1.75vw, 30px);
  letter-spacing: 0.16em;
  color: #fff;
  text-decoration: none;
  line-height: 1;
}
.ec-nav-right {
  display: flex;
  align-items: center;
  gap: clamp(24px, 3.2vw, 62px);
}
.ec-links {
  display: flex;
  align-items: center;
  gap: clamp(20px, 2.8vw, 56px);
}
.ec-link {
  font-family: var(--font-mono);
  font-weight: 400;
  font-size: clamp(11px, 0.78vw, 14px);
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #fff;
  text-decoration: none;
  transition: color 0.25s ease;
}
.ec-link:hover { color: var(--text-dim); }
.ec-link:focus-visible { outline: 1px solid rgba(255,255,255,0.7); outline-offset: 3px; }

.ec-cta-nav {
  font-family: var(--font-mono);
  font-weight: 400;
  font-size: clamp(11px, 0.78vw, 14px);
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #fff;
  text-decoration: none;
  padding: clamp(12px, 1vw, 17px) clamp(20px, 1.8vw, 32px);
  border: 1px solid var(--line-strong);
  transition: background 0.25s ease, border-color 0.25s ease;
  white-space: nowrap;
}
.ec-cta-nav:hover { background: var(--fill-ghost); border-color: rgba(255,255,255,0.5); }
.ec-cta-nav:focus-visible { outline: 1px solid rgba(255,255,255,0.7); outline-offset: 3px; }

/* Hamburger */
.ec-hamburger {
  display: none;
  position: relative;
  width: 44px;
  height: 44px;
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  flex-shrink: 0;
}
.ec-bar {
  position: absolute;
  left: 50%;
  width: 22px;
  height: 1px;
  background: #fff;
  transform-origin: center;
  transition: transform 0.45s var(--ease-premium), opacity 0.25s ease, background 0.2s ease;
}
.ec-bar:nth-child(1) { top: 16px; transform: translateX(-50%); }
.ec-bar:nth-child(2) { top: 22px; transform: translateX(-50%); }
.ec-bar:nth-child(3) { top: 28px; transform: translateX(-50%); }
.ec-hamburger.is-open .ec-bar:nth-child(1) { transform: translateX(-50%) translateY(6px) rotate(45deg); }
.ec-hamburger.is-open .ec-bar:nth-child(2) { opacity: 0; transform: translateX(-50%) scaleX(0); }
.ec-hamburger.is-open .ec-bar:nth-child(3) { transform: translateX(-50%) translateY(-6px) rotate(-45deg); }
.ec-hamburger:focus-visible { outline: 1px solid rgba(255,255,255,0.7); outline-offset: 3px; }

@media (max-width: 900px) {
  .ec-links, .ec-cta-nav { display: none; }
  .ec-hamburger { display: block; }
}

/* Mobile menu */
.ec-mmenu {
  position: fixed;
  inset: 0;
  z-index: 50;
  background: rgba(4,4,6,0.94);
  backdrop-filter: blur(28px) saturate(140%);
  -webkit-backdrop-filter: blur(28px) saturate(140%);
  display: flex;
  align-items: center;
  justify-content: center;
  clip-path: circle(3% at calc(100% - 42px) 42px);
  opacity: 0;
  pointer-events: none;
  transition: clip-path 0.7s var(--ease-premium), opacity 0.45s ease;
}
.ec-mmenu.is-open {
  clip-path: circle(150% at calc(100% - 42px) 42px);
  opacity: 1;
  pointer-events: auto;
}
.ec-mmenu-nav {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 32px;
}
.ec-mmenu-link {
  font-family: var(--font-mono);
  font-weight: 400;
  font-size: clamp(20px, 5.5vw, 28px);
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #fff;
  text-decoration: none;
  opacity: 0;
  transform: translateY(16px);
  transition:
    opacity 0.4s ease,
    transform 0.5s var(--ease-premium),
    color 0.2s ease;
  transition-delay: calc(180ms + var(--i, 0) * 70ms);
}
.ec-mmenu.is-open .ec-mmenu-link { opacity: 1; transform: translateY(0); }
.ec-mmenu-link:hover { color: var(--text-dim); }
.ec-mmenu-link:focus-visible { outline: 1px solid rgba(255,255,255,0.7); outline-offset: 3px; }

.ec-mmenu-cta {
  font-family: var(--font-mono);
  font-weight: 400;
  font-size: clamp(14px, 2vw, 18px);
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: #fff;
  text-decoration: none;
  padding: 16px 40px;
  border: 1px solid var(--line-strong);
  opacity: 0;
  transform: translateY(16px);
  transition:
    opacity 0.4s ease,
    transform 0.5s var(--ease-premium),
    background 0.25s ease;
  transition-delay: calc(180ms + var(--i, 4) * 70ms);
}
.ec-mmenu.is-open .ec-mmenu-cta { opacity: 1; transform: translateY(0); }
.ec-mmenu-cta:hover { background: var(--fill-ghost); }
.ec-mmenu-cta:focus-visible { outline: 1px solid rgba(255,255,255,0.7); outline-offset: 3px; }

/* Body */
.ec-body {
  position: relative;
  z-index: 3;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: clamp(12px,2vh,28px) clamp(28px, 7vw, 140px) clamp(64px,9vh,104px) var(--gutter);
  min-height: 0;
  overflow-y: auto;
}
@media (max-width: 720px) {
  .ec-body { justify-content: center; padding: clamp(12px,2vh,28px) var(--gutter) clamp(72px,10vh,110px); }
}

/* Panel */
.ec-panel {
  width: min(42vw, 660px);
  min-width: 340px;
  max-width: 100%;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}
@media (max-width: 1100px) {
  .ec-panel { width: min(72vw, 540px); min-width: 0; }
}
@media (max-width: 720px) {
  .ec-panel { width: 100%; min-width: 0; }
}

/* Chip */
.ec-chip {
  font-family: var(--font-mono);
  font-weight: 400;
  font-size: clamp(11px, 0.72vw, 14px);
  letter-spacing: 0.2em;
  text-transform: uppercase;
  background: rgba(255,255,255,0.09);
  padding: clamp(9px, 0.8vw, 14px) clamp(14px, 1.1vw, 20px);
  line-height: 1;
  color: #fff;
  border-radius: 0;
}

/* H1 — sized to fit inside .ec-panel; "VOICECAST" must never clip */
.ec-h1 {
  font-family: var(--font-display);
  font-weight: 200;
  font-size: clamp(34px, 4.4vw, 66px);
  letter-spacing: 0.02em;
  line-height: 0.98;
  margin-top: clamp(24px, 2.6vw, 44px);
  color: #fff;
  max-width: 100%;
  overflow-wrap: break-word;
}
@media (max-width: 380px) {
  .ec-h1 { font-size: clamp(34px, 12vw, 48px); }
}

/* Tagline */
.ec-tagline {
  font-family: var(--font-mono);
  font-weight: 300;
  font-size: clamp(11px, 0.94vw, 17px);
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--text-dim);
  margin-top: clamp(14px, 1.4vw, 24px);
  line-height: 1.4;
}

/* Form */
.ec-form {
  margin-top: clamp(38px, 4.6vw, 82px);
  display: flex;
  flex-direction: column;
  gap: clamp(14px, 1.3vw, 22px);
  width: 100%;
}
.ec-sr-only {
  position: absolute;
  width: 1px; height: 1px;
  padding: 0; margin: -1px;
  overflow: hidden;
  clip: rect(0,0,0,0);
  white-space: nowrap;
  border-width: 0;
}
.ec-field { width: 100%; }
.ec-input {
  width: 100%;
  box-sizing: border-box;
  background: transparent;
  border: none;
  border-bottom: 1px solid var(--line-strong);
  border-radius: 0;
  padding: 0 2px clamp(12px, 1.1vw, 18px);
  font-family: var(--font-display);
  font-weight: 300;
  font-size: clamp(16px, 0.95vw, 18px);
  color: #fff;
  outline: none;
  transition: border-color 0.25s ease;
}
.ec-input::placeholder { color: var(--text-dim); }
.ec-input:focus { border-bottom-color: rgba(255,255,255,0.85); }
.ec-input:focus::placeholder { color: var(--text-dimmer); }
.ec-input:focus-visible { outline: 1px solid rgba(255,255,255,0.7); outline-offset: 3px; }

.ec-btn {
  width: 100%;
  border-radius: 0;
  border: none;
  padding: clamp(17px, 1.6vw, 27px) 20px;
  font-family: var(--font-mono);
  font-weight: 400;
  font-size: clamp(11px, 0.78vw, 14px);
  letter-spacing: 0.22em;
  text-transform: uppercase;
  cursor: pointer;
  transition: background 0.25s ease, color 0.25s ease;
}
.ec-btn:focus-visible { outline: 1px solid rgba(255,255,255,0.7); outline-offset: 3px; }
.ec-btn--ghost { background: var(--fill-ghost); color: var(--text-dimmer); }
.ec-btn--ghost:hover { background: rgba(255,255,255,0.09); color: #fff; }
.ec-btn--solid { background: var(--fill-solid); color: #fff; }
.ec-btn--solid:hover { background: rgba(255,255,255,0.17); }

/* Back button */
.ec-back {
  font-family: var(--font-mono);
  font-weight: 400;
  font-size: clamp(11px, 0.74vw, 13px);
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--text-dim);
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  margin-bottom: clamp(18px, 1.8vw, 30px);
  transition: color 0.2s ease;
}
.ec-back:hover { color: #fff; }

/* Form title */
.ec-form-title {
  font-family: var(--font-display);
  font-weight: 200;
  font-size: clamp(28px, 3vw, 52px);
  letter-spacing: 0.04em;
  line-height: 1;
  color: #fff;
  margin: 0 0 clamp(28px, 3vw, 48px);
}

/* Form-level error -- wrong credentials, duplicate email, validation, or a
   network/server failure reaching the backend. */
.ec-error {
  font-family: var(--font-mono);
  font-weight: 400;
  font-size: clamp(11px, 0.78vw, 13px);
  letter-spacing: 0.04em;
  color: #ff8a8a;
  background: rgba(255, 90, 90, 0.08);
  border: 1px solid rgba(255, 90, 90, 0.28);
  border-radius: 0;
  padding: clamp(10px, 1vw, 14px) clamp(12px, 1.1vw, 16px);
  margin-top: clamp(10px, 1vw, 16px);
  width: 100%;
  box-sizing: border-box;
}
.ec-btn:disabled { opacity: 0.55; cursor: not-allowed; }

/* Switch row */
.ec-switch {
  font-family: var(--font-mono);
  font-weight: 300;
  font-size: clamp(11px, 0.74vw, 13px);
  letter-spacing: 0.12em;
  color: var(--text-dim);
  margin-top: clamp(18px, 1.8vw, 32px);
  width: 100%;
}
.ec-switch-link {
  font-family: var(--font-mono);
  font-weight: 400;
  font-size: clamp(11px, 0.74vw, 13px);
  letter-spacing: 0.12em;
  color: #fff;
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  text-decoration: underline;
  text-underline-offset: 3px;
  transition: color 0.2s ease;
}
.ec-switch-link:hover { color: var(--text-dim); }

/* Referral */
.ec-referral {
  font-family: var(--font-mono);
  font-weight: 400;
  font-size: clamp(11px, 0.74vw, 14px);
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #fff;
  text-decoration: none;
  margin-top: clamp(26px, 2.6vw, 46px);
  align-self: center;
  transition: color 0.25s ease;
}
.ec-referral:hover { color: var(--text-dim); text-decoration: underline; text-underline-offset: 4px; }
.ec-referral:focus-visible { outline: 1px solid rgba(255,255,255,0.7); outline-offset: 3px; }

/* Footer — overlays the bottom of the hero, no divider line */
.ec-footer {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 4;
  padding: clamp(16px, 1.6vw, 26px) var(--gutter);
  padding-bottom: max(clamp(16px, 1.6vw, 26px), env(safe-area-inset-bottom, 0px));
  text-align: center;
  background: linear-gradient(to top, rgba(0,0,0,0.9) 0%, rgba(0,0,0,0.5) 55%, transparent 100%);
}
.ec-legal {
  font-family: var(--font-display);
  font-weight: 300;
  font-size: clamp(12px, 0.82vw, 16px);
  color: var(--text-dim);
  line-height: 1.5;
  margin: 0;
}
.ec-legal-link {
  color: #fff;
  text-decoration: underline;
  text-decoration-thickness: 1px;
  text-underline-offset: 3px;
  transition: color 0.25s ease;
}
.ec-legal-link:hover { color: var(--text-dim); }

/* Hero image — upper-left, above/around VOICECAST logo */



/* Full-screen hero image — single soft mask, no composite seam */
.ec-left-img {
  position: absolute;
  inset: 0;
  z-index: 1;
  pointer-events: none;
  overflow: hidden;
  background: #000;
}
.ec-left-img img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: 30% center;
  display: block;
  filter: brightness(0.52) contrast(1.1) saturate(0.68);
  -webkit-mask-image: radial-gradient(ellipse 100% 108% at 30% 48%,
    #000 0%, #000 34%, rgba(0,0,0,0.6) 58%, rgba(0,0,0,0.22) 74%, transparent 88%);
  mask-image: radial-gradient(ellipse 100% 108% at 30% 48%,
    #000 0%, #000 34%, rgba(0,0,0,0.6) 58%, rgba(0,0,0,0.22) 74%, transparent 88%);
}
@media (max-width: 720px) {
  .ec-left-img img { object-position: 44% center; }
}

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}

/* Short-height compress */
@media (max-height: 640px) {
  .ec-nav { padding-top: clamp(12px, 1.5vw, 20px); padding-bottom: clamp(12px, 1.5vw, 20px); }
  .ec-h1 { font-size: clamp(36px, 7vw, 64px); }
  .ec-form { margin-top: clamp(20px, 2vw, 40px); gap: clamp(8px, 0.8vw, 14px); }
  .ec-btn { padding: clamp(10px, 1vw, 16px) 20px; }
  .ec-footer .ec-legal { font-size: 11px; }
}
`;

type AuthView = "home" | "signup" | "login" | "forgot";

export default function EchoLanding({ enter }: { enter: () => void }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [view, setView] = useState<AuthView>("home");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [forgotEmail, setForgotEmail] = useState("");
  const [forgotSent, setForgotSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const toggleRef = useRef<HTMLButtonElement>(null);

  const resetFields = () => { setName(""); setEmail(""); setPassword(""); setError(null); };
  const goView = (v: AuthView) => { resetFields(); setView(v); };

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!name.trim()) return setError("Enter your name.");
    if (password.length < 8) return setError("Password must be at least 8 characters.");
    setSubmitting(true);
    try {
      await signup(email, password, name.trim());
      enter();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server. Try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      enter();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server. Try again.");
    } finally {
      setSubmitting(false);
    }
  };

  useEffect(() => {
    const onResize = () => { if (window.innerWidth >= 901) setMenuOpen(false); };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && menuOpen) {
        setMenuOpen(false);
        toggleRef.current?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  useEffect(() => {
    document.body.style.overflow = menuOpen ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [menuOpen]);

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: CSS }} />
      <section className="ec-hero">
        {/* Scrim */}
        <div className="ec-scrim" aria-hidden="true" />

        {/* Left image — AI robot at mic */}
        <div className="ec-left-img" aria-hidden="true">
          <img src={robotImg} alt="" />
        </div>

        {/* Navbar */}
        <nav className="ec-nav" aria-label="Main navigation">
          <a href="#" className="ec-logo" onClick={e => e.preventDefault()}>VOICECAST</a>
          <div className="ec-nav-right">
            <div className="ec-links">
              {NAV_LINKS.map(l => (
                <a key={l.href} href={l.href} className="ec-link">{l.label}</a>
              ))}
            </div>
            <button
              ref={toggleRef}
              className={`ec-hamburger${menuOpen ? " is-open" : ""}`}
              aria-expanded={menuOpen}
              aria-controls="ec-mobile-menu"
              aria-label={menuOpen ? "Close menu" : "Open menu"}
              onClick={() => setMenuOpen(o => !o)}
            >
              <span className="ec-bar" />
              <span className="ec-bar" />
              <span className="ec-bar" />
            </button>
          </div>
        </nav>

        {/* Mobile menu */}
        <div
          id="ec-mobile-menu"
          ref={menuRef}
          className={`ec-mmenu${menuOpen ? " is-open" : ""}`}
          role="dialog"
          aria-modal="true"
          aria-label="Site menu"
          aria-hidden={!menuOpen}
          onClick={e => { if (e.target === menuRef.current) setMenuOpen(false); }}
        >
          <nav className="ec-mmenu-nav">
            {NAV_LINKS.map((l, i) => (
              <a
                key={l.href}
                href={l.href}
                className="ec-mmenu-link"
                style={{ "--i": i } as React.CSSProperties}
                onClick={() => setMenuOpen(false)}
              >
                {l.label}
              </a>
            ))}
          </nav>
        </div>

        {/* Hero body */}
        <div className="ec-body">
          <div className="ec-panel">

            {/* ── HOME ── */}
            {view === "home" && <>
              <h1 className="ec-h1">VOICECAST</h1>
              <p className="ec-tagline">Don&apos;t just translate. Perform.</p>
              <div className="ec-form">
                <button type="button" className="ec-btn ec-btn--ghost" onClick={() => goView("signup")}>
                  Sign Up
                </button>
                <button type="button" className="ec-btn ec-btn--solid" onClick={() => goView("login")}>
                  Login
                </button>
              </div>
            </>}

            {/* ── SIGN UP ── */}
            {view === "signup" && <>
              <button className="ec-back" onClick={() => goView("home")}>← Back</button>
              <h2 className="ec-form-title">Create account</h2>
              <form className="ec-form" noValidate onSubmit={handleSignup}>
                <div className="ec-field">
                  <label htmlFor="ec-name" className="ec-sr-only">Full name</label>
                  <input id="ec-name" type="text" className="ec-input" placeholder="Full name"
                    value={name} onChange={e => { setName(e.target.value); setError(null); }} autoComplete="name" required />
                </div>
                <div className="ec-field">
                  <label htmlFor="ec-su-email" className="ec-sr-only">Email</label>
                  <input id="ec-su-email" type="email" className="ec-input" placeholder="Email"
                    value={email} onChange={e => { setEmail(e.target.value); setError(null); }} autoComplete="email" required />
                </div>
                <div className="ec-field">
                  <label htmlFor="ec-su-pw" className="ec-sr-only">Password</label>
                  <input id="ec-su-pw" type="password" className="ec-input" placeholder="Password (min. 8 characters)"
                    value={password} onChange={e => { setPassword(e.target.value); setError(null); }} autoComplete="new-password" required />
                </div>
                {error && <div className="ec-error" role="alert">{error}</div>}
                <button type="submit" className="ec-btn ec-btn--solid" disabled={submitting}>
                  {submitting ? "Creating account…" : "Create account"}
                </button>
              </form>
              <p className="ec-switch">
                Already have an account?{" "}
                <button className="ec-switch-link" onClick={() => goView("login")}>Log in</button>
              </p>
            </>}

            {/* ── LOGIN ── */}
            {view === "login" && <>
              <button className="ec-back" onClick={() => goView("home")}>← Back</button>
              <h2 className="ec-form-title">Welcome back</h2>
              <form className="ec-form" noValidate onSubmit={handleLogin}>
                <div className="ec-field">
                  <label htmlFor="ec-li-email" className="ec-sr-only">Email</label>
                  <input id="ec-li-email" type="email" className="ec-input" placeholder="Email"
                    value={email} onChange={e => { setEmail(e.target.value); setError(null); }} autoComplete="email" required />
                </div>
                <div className="ec-field">
                  <label htmlFor="ec-li-pw" className="ec-sr-only">Password</label>
                  <input id="ec-li-pw" type="password" className="ec-input" placeholder="Password"
                    value={password} onChange={e => { setPassword(e.target.value); setError(null); }} autoComplete="current-password" required />
                </div>
                {error && <div className="ec-error" role="alert">{error}</div>}
                <button type="submit" className="ec-btn ec-btn--solid" disabled={submitting}>
                  {submitting ? "Logging in…" : "Log in"}
                </button>
              </form>
              <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",width:"100%"}}>
                <p className="ec-switch">
                  No account?{" "}
                  <button className="ec-switch-link" onClick={() => goView("signup")}>Sign up</button>
                </p>
                <button className="ec-switch-link" style={{marginTop:"clamp(18px,1.8vw,32px)"}}
                  onClick={() => goView("forgot")}>Forgot password</button>
              </div>
            </>}

            {/* ── FORGOT PASSWORD ── */}
            {view === "forgot" && <>
              <button className="ec-back" onClick={() => goView("login")}>← Back to login</button>
              <h2 className="ec-form-title">Reset password</h2>
              {forgotSent ? (
                <p className="ec-tagline" style={{marginTop:"clamp(24px,2vw,40px)"}}>
                  Check your inbox — a reset link is on its way.
                </p>
              ) : (
                <form className="ec-form" noValidate onSubmit={e => { e.preventDefault(); setForgotSent(true); }}>
                  <div className="ec-field">
                    <label htmlFor="ec-fp-email" className="ec-sr-only">Email</label>
                    <input id="ec-fp-email" type="email" className="ec-input" placeholder="Email"
                      value={forgotEmail} onChange={e => setForgotEmail(e.target.value)} autoComplete="email" required />
                  </div>
                  <button type="submit" className="ec-btn ec-btn--solid">Send reset link</button>
                </form>
              )}
            </>}

          </div>
        </div>

        {/* Legal footer */}
        <footer className="ec-footer">
          <p className="ec-legal">
            Opening a VoiceCast account signals that you accept our{" "}
            <a href="#privacy-notice" className="ec-legal-link">Privacy Notice</a>
            {" "}and{" "}
            <a href="#service-contract" className="ec-legal-link">Service Contract</a>.
          </p>
        </footer>
      </section>
    </>
  );
}
