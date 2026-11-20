import { useState, useEffect } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { useAuth } from "@/lib/AuthContext";
import { useConsent } from "@/lib/ConsentContext";
import { ConsentDisclaimer } from "@/components/AdultConsent";
import EmailAuthDialog from "@/components/EmailAuthDialog";
import LandingAudio from "@/components/LandingAudio";
import { useNavigate } from "react-router-dom";
import "@/styles/landing.css";

export default function SplashScreen({ active = true }) {
  const { status } = useConsent();
  const { user, login, loginBusy, loginError, cancelLogin, previewLogin, loading } = useAuth();
  const [authOpen, setAuthOpen] = useState(false);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const previewEnabled = process.env.REACT_APP_ENABLE_PREVIEW_LOGIN === "true";
  const navigate = useNavigate();
  const enter = () => {
    if (status !== "accepted" || loading) return;
    if (user) navigate("/studio", { replace: true });
    else setAuthOpen(true);
  };
  const enterGoogle = () => {
    if (status !== "accepted") return;
    setPreviewError("");
    login();
  };
  const enterPreview = async () => {
    if (status !== "accepted") return;
    setPreviewBusy(true); setPreviewError("");
    try { await previewLogin(); }
    catch (e) {
      const code = e?.response?.status;
      if (code === 401 && e?.response?.data?.detail === "Not authenticated") setPreviewError("The preview session couldn't be verified: the session did not reach the server. Retry or open the app in a new tab.");
      else if (code === 401) setPreviewError("The preview session couldn't be verified. Please retry or open the app in a new tab.");
      else if (code === 404) setPreviewError("Preview sign-in is disabled on the server.");
      else if (!e?.response && (e?.code === "ERR_NETWORK" || e?.code === "ECONNABORTED")) setPreviewError("Can't reach the preview server. Check the connection and try again.");
      else setPreviewError(e?.response?.data?.detail || e?.message || "Preview sign-in is unavailable.");
    } finally { setPreviewBusy(false); }
  };
  useEffect(() => {
    if (authOpen && !loading && user && status === "accepted") navigate("/studio", { replace: true });
  }, [authOpen, user, loading, status, navigate]);
  useEffect(() => { if (status !== "accepted") setAuthOpen(false); }, [status]);

  return <div className="splash" data-testid="splash-screen" style={{ "--splash-bg": "url('/assets/splash_bg.png')" }}>
    <LandingAudio active={active} />
    <Dialog.Root open={active && !authOpen}>
      <Dialog.Portal>
        <Dialog.Overlay className="landing-consent-overlay" />
        <Dialog.Content className="splash-card landing-consent-card" data-testid="splash-consent-panel"
          onEscapeKeyDown={(event) => event.preventDefault()} onPointerDownOutside={(event) => event.preventDefault()}>
          <Dialog.Title className="landing-consent-title">Before you enter <span>· DA ROASTBOX!</span></Dialog.Title>
          <Dialog.Description className="landing-consent-description">Please review and accept the disclaimer.</Dialog.Description>
          <ConsentDisclaimer />
          <button type="button" className="landing-google landing-enter" onClick={enter}
            disabled={status !== "accepted" || loading} data-testid="enter-roast-btn">
            Enter the Roast <span aria-hidden="true">→</span>
          </button>
          {loginError && <p role="alert" data-testid="google-login-error" className="landing-error">{loginError}</p>}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
    <Dialog.Root open={active && authOpen} onOpenChange={(next) => {
      if (!next && (loginBusy || previewBusy)) return;
      setAuthOpen(next);
    }}>
      <Dialog.Portal>
        <Dialog.Overlay className="landing-auth-overlay" />
        <Dialog.Content className="landing-auth-dialog" data-testid="sign-in-dialog"
          onEscapeKeyDown={(event) => { if (loginBusy || previewBusy) event.preventDefault(); }}
          onPointerDownOutside={(event) => { if (loginBusy || previewBusy) event.preventDefault(); }}>
          <div className="landing-auth-top"><span>DA ROASTBOX / BACKSTAGE</span>
            <Dialog.Close asChild><button type="button" className="landing-auth-close" aria-label="Close sign in" disabled={loginBusy || previewBusy}><X size={19} /></button></Dialog.Close>
          </div>
          <Dialog.Title className="landing-auth-title">Your seat is waiting.</Dialog.Title>
          <Dialog.Description className="landing-auth-description">Sign in or create an account to keep your roasts and credits together.</Dialog.Description>
          <button className="landing-google" disabled={loginBusy || previewBusy || status !== "accepted"} onClick={enterGoogle} data-testid="splash-login-btn">
            <span className="landing-google-mark" aria-hidden="true">G</span>
            {loginBusy ? "Waiting for Google…" : "Continue with Google"}
          </button>
          <EmailAuthDialog disabled={loginBusy || previewBusy || status !== "accepted"} />
          {loginBusy && <p role="status" className="landing-status">Complete sign-in in the Google window. {" "}<button type="button" onClick={cancelLogin} className="btn-ghost">Cancel</button></p>}
          {loginError && <p role="alert" data-testid="google-login-error" className="landing-error">{loginError}</p>}
          {previewEnabled && <div className="landing-preview">
            <button className="landing-preview-btn" disabled={previewBusy || loginBusy || status !== "accepted"} onClick={enterPreview} data-testid="preview-login-btn">
              {previewBusy ? "Entering preview…" : "Explore the preview →"}
            </button>
            <p>Isolated test account · preview credits only · real purchases disabled.</p>
            {previewError && <p role="alert" data-testid="preview-login-error" className="landing-error">{previewError}</p>}
          </div>}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  </div>;
}
