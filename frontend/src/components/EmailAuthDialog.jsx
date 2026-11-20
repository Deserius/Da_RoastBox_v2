import { useEffect, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { ArrowLeft, Mail, X } from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import "@/styles/email-auth.css";

function messageFor(error) {
  const code = error?.response?.status;
  if (code === 401) return "That email or password didn't match. Please try again.";
  if (code === 422) return "Please check your email address and password and try again.";
  if (code === 429) return "Too many attempts. Please wait before trying again.";
  if (code === 503) return "Email sign-in or delivery isn't available right now. Please try again later.";
  return "We couldn't complete that request. Check your connection and try again.";
}

export default function EmailAuthDialog({ disabled }) {
  const { emailLogin } = useAuth();
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState("login");
  const [availability, setAvailability] = useState(null);
  const [availabilityError, setAvailabilityError] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return undefined;
    const controller = new AbortController();
    setAvailability(null); setAvailabilityError(false);
    api.get("/auth/email/status", { signal: controller.signal }).then(({ data }) => setAvailability(data))
      .catch(() => { if (!controller.signal.aborted) setAvailabilityError(true); });
    return () => controller.abort();
  }, [open]);
  const changeMode = (next) => { setMode(next); setPassword(""); setDone(""); setError(""); };
  const onOpenChange = (next) => {
    if (!next && busy) return;
    setOpen(next);
    if (!next) { setPassword(""); setError(""); setDone(""); setMode("login"); }
  };
  const submit = async (event) => {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      if (mode === "login") {
        await emailLogin(email, password);
        setPassword(""); setOpen(false);
      } else {
        const { data } = await api.post(`/auth/email/${mode === "signup" ? "register" : "forgot"}`, { email });
        setDone(data.message || "If the address can be used, an email with next steps will arrive shortly.");
      }
    } catch (e) { setError(messageFor(e)); }
    finally { setBusy(false); }
  };
  const canProceed = availability && (mode === "login" ? availability.login_available :
    mode === "signup" ? availability.registration_available : availability.recovery_available);
  const heading = mode === "signup" ? "Join the show." : mode === "forgot" ? "Let's get you back in." : "Welcome backstage.";
  return <Dialog.Root open={open} onOpenChange={onOpenChange}>
    <Dialog.Trigger asChild><button type="button" className="landing-email" disabled={disabled} data-testid="email-auth-open"><Mail size={17} aria-hidden="true" /> Continue with email</button></Dialog.Trigger>
    <Dialog.Portal><Dialog.Overlay className="email-overlay">
      <Dialog.Content className="email-dialog" data-testid="email-auth-dialog" onEscapeKeyDown={(event) => { if (busy) event.preventDefault(); }}
        onPointerDownOutside={(event) => { if (busy) event.preventDefault(); }}>
        <div className="email-dialog-top"><span>DA ROASTBOX / ACCOUNT</span><Dialog.Close asChild><button type="button" className="email-close" aria-label="Close email sign-in" disabled={busy}><X size={19} /></button></Dialog.Close></div>
        <Dialog.Title className="email-title">{heading}</Dialog.Title>
        <Dialog.Description className="email-description">{mode === "signup" ? "We'll email a secure link so you can choose your password." : mode === "forgot" ? "We'll send recovery instructions to your email." : "Sign in with the email address you verified."}</Dialog.Description>
        {!availability && !availabilityError && <p className="email-hint" role="status">Checking email sign-in…</p>}
        {availabilityError && <p className="email-error" role="alert">Couldn't reach the sign-in service. Please close this window and try again.</p>}
        {availability && !canProceed && <div className="email-not-configured" role="status">
          {mode === "login" && !availability.login_available ? "Email sign-in has not been configured by the app administrator yet." : "Email delivery is not configured yet, so account setup and password recovery are unavailable."}
        </div>}
        {canProceed && (done ? <div className="email-success" role="status"><strong>Check your inbox.</strong><p>{done}</p><button type="button" onClick={() => changeMode("login")} className="email-back">Back to sign in</button></div> :
          <form onSubmit={submit} className="email-form">
            <label>Email address<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" maxLength={254} required data-testid="email-address" /></label>
            {mode === "login" && <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" maxLength={128} required data-testid="email-password" /></label>}
            {mode === "signup" && <p className="email-hint">Already use Google with this email? After mailbox verification, email sign-in will use the same account.</p>}
            {error && <p className="email-error" role="alert" data-testid="email-auth-error">{error}</p>}
            <button type="submit" className="email-submit" disabled={busy} data-testid="email-auth-submit">{busy ? "Please wait…" : mode === "login" ? "Sign in" : mode === "signup" ? "Email my setup link" : "Email recovery instructions"}</button>
          </form>)}
        <div className="email-mode-links">
          {mode !== "login" ? <button type="button" onClick={() => changeMode("login")} disabled={busy}><ArrowLeft size={14} aria-hidden="true" /> Back to sign in</button> : <>
            <button type="button" onClick={() => changeMode("signup")} disabled={busy} data-testid="email-create-account">Create an account</button>
            <button type="button" onClick={() => changeMode("forgot")} disabled={busy} data-testid="email-forgot-password">Forgot password?</button>
          </>}
        </div>
      </Dialog.Content>
    </Dialog.Overlay></Dialog.Portal>
  </Dialog.Root>;
}
