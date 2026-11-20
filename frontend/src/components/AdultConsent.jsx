import { useConsent } from "@/lib/ConsentContext";
import "@/styles/consent.css";

// The original disclaimer and explicit checkbox are shared by the splash
// consent panel and protected/direct-link gate.
export function ConsentDisclaimer() {
  const { status, accept, decline } = useConsent();
  return (
    <section className="disclaimer inline-disclaimer" aria-labelledby="disclaimer-title" data-testid="inline-disclaimer">
      <strong id="disclaimer-title">18+ ENTERTAINMENT — DISCLAIMER</strong>
      <p>
        This app generates uncensored, adult comedic roast content for entertainment only.
        By using Da RoastBox you agree the app and its creators are not liable for content
        generated or user actions. Do not target protected classes or harass real individuals.
        Roast responsibly.
      </p>
      <label className="checkbox-row">
        <input type="checkbox" checked={status === "accepted"}
          onChange={(event) => event.target.checked ? accept() : decline()}
          data-testid="disclaimer-checkbox" />
        <span>I'm 18+, I agree to the disclaimer and Terms of Use.</span>
      </label>
    </section>
  );
}

// Direct protected/share links still require an explicit choice, without a popup.
export function ConsentGate({ children }) {
  const { status } = useConsent();
  if (status === "accepted") return children;
  return (
    <main className="consent-gate-backdrop" style={{ "--splash-bg": "url('/assets/splash_bg.png')" }}>
      <div className="consent-gate-card">
        <h1>DA ROASTBOX!</h1>
        <p>Please review the disclaimer before continuing.</p>
        <ConsentDisclaimer />
      </div>
    </main>
  );
}
