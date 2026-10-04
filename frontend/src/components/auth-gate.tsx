"use client";

import { Activity, KeyRound, ShieldCheck } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { API_BASE, getAuthStatus, login, logout, setupAccount } from "@/lib/api";
import { Dashboard } from "@/components/dashboard";

export function AuthGate() {
  const [ready, setReady] = useState(false);
  const [setup, setSetup] = useState(false);
  const [username, setUsername] = useState("AtharvaKh");
  const [authenticated, setAuthenticated] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [googleEnabled, setGoogleEnabled] = useState(false);
  const [setupToken, setSetupToken] = useState("");
  useEffect(() => {
    getAuthStatus().then((status) => {
      setSetup(status.setup_required);
      setAuthenticated(status.authenticated);
      setGoogleEnabled(Boolean(status.google_enabled));
      if (status.username) setUsername(status.username);
    }).catch((caught: unknown) => setError(caught instanceof Error ? caught.message : "Authentication service unavailable."))
      .finally(() => setReady(true));
    const authError = new URLSearchParams(window.location.search).get("auth_error");
    if (authError) setError(authError === "google_email_not_allowed" ? "This Google account is not allowed for this private workspace." : "Google sign-in could not be completed. Check OAuth setup and try again.");
  }, []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const data = new FormData(event.currentTarget);
    const user = "AtharvaKh";
    const password = String(data.get("password") ?? "");
    try {
      if (setup) { await setupAccount(user, password, setupToken); setSetupToken(""); } else await login(user, password);
      setUsername(user); setAuthenticated(true);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Could not authenticate."); }
    finally { setBusy(false); }
  }
  if (!ready) return <div className="auth-screen"><div className="auth-card"><Activity className="auth-mark" /><p>Checking local account…</p></div></div>;
  if (!authenticated) return <main className="auth-screen"><section className="auth-card">
    <div className="auth-brand"><span className="brand-mark"><Activity size={21} /></span><div>MARKET<span>DESK</span></div></div>
    <div className="auth-icon"><ShieldCheck size={20} /></div>
    <p className="auth-eyebrow">PRIVATE RESEARCH WORKSPACE</p>
    <h1>{setup ? "Create your local account" : "Welcome back"}</h1>
    <p className="auth-copy">{setup ? "Create the one administrator account for this private workspace." : "Sign in to open the private market intelligence workspace."}</p>
    <form onSubmit={submit}>
      <label>Administrator account<input name="username" autoComplete="username" value="AtharvaKh" readOnly aria-readonly="true" /></label>
      <label>Password<input name="password" type="password" autoComplete={setup ? "new-password" : "current-password"} minLength={setup ? 12 : undefined} maxLength={256} required /></label>
      {setup && <><label>Administrator setup token<input name="setup_token" type="password" autoComplete="off" minLength={16} required value={setupToken} onChange={(event) => setSetupToken(event.target.value)} /></label><small className="auth-hint">Set AUTH_SETUP_TOKEN privately on the API host first. Only the AtharvaKh administrator account can be created. Use a password with at least 12 characters.</small></>}
      {error && <div className="auth-error" role="alert">{error}</div>}
      <button className="auth-submit" disabled={busy}><KeyRound size={16} />{busy ? "Please wait…" : setup ? "Create account" : "Sign in"}</button>
    </form>
    <div className="google-auth"><div className="auth-divider"><span>OR</span></div><button type="button" disabled={!googleEnabled} onClick={() => window.location.assign(`${API_BASE}/api/v1/auth/google/start`)}><GoogleMark />Continue with Google</button><small>{googleEnabled ? "Sign-in is restricted to the Google email configured for this private workspace." : "To enable: configure GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI, and GOOGLE_ALLOWED_EMAIL in the project .env."}</small></div>
    <div className="auth-foot">Local single-user mode · HttpOnly signed session · No trading access</div>
  </section></main>;
  return <Dashboard onLogout={async () => { await logout(); setAuthenticated(false); setSetup(false); }} username={username} />;
}

function GoogleMark() {
  return <svg aria-hidden="true" width="17" height="17" viewBox="0 0 48 48"><path fill="#FFC107" d="M43.6 24.5c0-1.4-.1-2.7-.4-4H24v7.6h11a9.4 9.4 0 0 1-4.1 6.2v5.1h6.6c3.9-3.6 6.1-8.8 6.1-14.9Z"/><path fill="#34A853" d="M24 44c5.5 0 10.1-1.8 13.5-4.8l-6.6-5.1c-1.8 1.2-4.1 2-6.9 2-5.3 0-9.8-3.6-11.4-8.4H5.8v5.3C9.1 39.6 16 44 24 44Z"/><path fill="#4A90E2" d="M12.6 27.7a12 12 0 0 1 0-7.4V15H5.8a20 20 0 0 0 0 18l6.8-5.3Z"/><path fill="#EA4335" d="M24 12.1c3 0 5.7 1 7.8 3.1l5.8-5.8C34.1 6 29.5 4 24 4 16 4 9.1 8.4 5.8 15l6.8 5.3c1.6-4.8 6.1-8.2 11.4-8.2Z"/></svg>;
}
