import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Flame, LockKeyhole } from "lucide-react";
import api from "@/lib/api";
import "@/styles/email-auth.css";

// Scrub a token fragment as soon as this module is loaded, before React mounts.
// It is held only in memory and is never written to storage, logs, or a query.
const captured = {};
function captureFragment() {
  const path = window.location.pathname;
  if (!/^\/auth\/(verify|reset)$/.test(path) || !window.location.hash) return;
  const candidate = new URLSearchParams(window.location.hash.slice(1)).get("token") || "";
  captured[path] = /^[A-Za-z0-9_-]{30,128}$/.test(candidate) ? candidate : "";
  try { window.history.replaceState(null, "", path + window.location.search); } catch { /* Restrictive browsers may refuse history changes. */ }
}
captureFragment();

export default function EmailTokenPage({ purpose }) {
  const navigate = useNavigate();
  const path = `/auth/${purpose}`;
  const [token] = useState(() => { captureFragment(); return captured[path] || ""; });
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  const isReset = purpose === "reset";
  const submit = async (event) => {
    event.preventDefault();
    if (password !== confirm) { setError("Those passwords don't match."); return; }
    if (password.length < 12 || password.length > 128) { setError("Use a password or passphrase between 12 and 128 characters."); return; }
    setBusy(true); setError("");
    try {
      await api.post(`/auth/email/${purpose}`, { token, password });
      delete captured[path];
      setPassword(""); setConfirm(""); setDone(true);
    } catch (e) {
      const status = e?.response?.status;
      if (status === 400) setError("This link is invalid, expired, or already used. Request a new one.");
      else if (status === 409) setError("This account can't be linked automatically. Contact support.");
      else if (status === 422) setError("Use a password or passphrase between 12 and 128 characters.");
      else if (status === 429) setError("Too many attempts. Please wait and try again.");
      else setError("This request couldn't be completed. Please try again later.");
    } finally { setBusy(false); }
  };
  return <main className="email-page" data-testid="email-token-page">
    <div className="email-page-card">
      <div className="email-page-brand"><Flame size={16} aria-hidden="true" /> DA ROASTBOX!</div>
      <div className="email-page-icon"><LockKeyhole size={22} aria-hidden="true" /></div>
      <h1>{done ? "You're all set." : isReset ? "Choose a new password." : "Finish setting up."}</h1>
      {done ? <>
        <p>{isReset ? "Your password has been changed and other sessions were signed out." : "Your email is verified. You can now sign in with your password."}</p>
        <button type="button" className="email-submit" onClick={() => navigate("/", { replace: true })}>Return to sign in <ArrowRight size={16} aria-hidden="true" /></button>
      </> : !token ? <>
        <p>This link is missing or expired. Return to sign in to request another email.</p>
        <button type="button" className="email-submit" onClick={() => navigate("/", { replace: true })}>Return to sign in</button>
      </> : <>
        <p>{isReset ? "Choose a new password for your account." : "Only the owner of this email link can choose the password. Use at least 12 characters."}</p>
        <form className="email-form" onSubmit={submit}>
          <label>New password<input type="password" autoComplete="new-password" minLength={12} maxLength={128} required value={password} onChange={(e) => setPassword(e.target.value)} data-testid="email-new-password" /></label>
          <label>Confirm password<input type="password" autoComplete="new-password" minLength={12} maxLength={128} required value={confirm} onChange={(e) => setConfirm(e.target.value)} data-testid="email-confirm-password" /></label>
          {error && <p className="email-error" role="alert" data-testid="email-token-error">{error}</p>}
          <button type="submit" className="email-submit" disabled={busy} data-testid="email-token-submit">{busy ? "Saving…" : isReset ? "Update password" : "Verify email & set password"}</button>
        </form>
      </>}
    </div>
  </main>;
}
