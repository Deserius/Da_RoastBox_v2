import { useEffect, useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import { useToast } from "@/lib/ToastContext";
import ProviderConsole from "@/components/ProviderConsole";

export default function SettingsPage() {
  const { user, refresh } = useAuth();
  const { toast } = useToast();
  const [openaiKey, setOpenaiKey] = useState("");
  const [elevenKey, setElevenKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [services, setServices] = useState(null);
  const [servicesError, setServicesError] = useState("");

  useEffect(() => {
    let active = true;
    api.get("/diagnostics").then(({ data }) => {
      if (active) setServices(data.config || {});
    }).catch(() => {
      if (active) setServicesError("Could not load service configuration. Check the app connection.");
    });
    return () => { active = false; };
  }, []);

  const aiStatus = user?.has_byok_openai ? "Personal key saved (not yet verified)"
    : user?.is_preview && services?.preview_hosted_ai_enabled ? `Hosted preview enabled: ${services.preview_hosted_daily_show_limit} shared show attempts per UTC day`
    : user?.is_preview ? "Add your own OpenAI key to use AI in preview"
    : (services?.emergent_llm_key || services?.openai_hosted_key) ? "Hosted key configured (not yet verified)" : "Not configured";
  const elevenStatus = user?.has_byok_elevenlabs ? "Personal key saved (not yet verified)"
    : (!user?.is_preview && services?.elevenlabs_hosted_key) ? "Hosted key configured (not yet verified)" : "Optional; OpenAI voice is the fallback";
  const paymentStatus = user?.is_preview ? "Purchases disabled in preview"
    : services?.stripe_api_key && services?.stripe_webhook_secret ? "Stripe configured (not yet verified)" : "Stripe key and/or webhook secret missing";

  const save = async () => {
    setBusy(true);
    try {
      await api.post("/voice-settings/keys", {
        openai_key: openaiKey || undefined,
        elevenlabs_key: elevenKey || undefined,
      });
      await refresh();
      setOpenaiKey(""); setElevenKey("");
      toast("Keys saved (encrypted at rest)", "success");
    } catch (e) {
      toast("Failed: " + (e?.response?.data?.detail || e.message), "error");
    } finally { setBusy(false); }
  };

  const clearAll = async () => {
    setBusy(true);
    try {
      await api.delete("/voice-settings/keys");
      await refresh();
      toast("BYOK keys cleared. Using app defaults.", "success");
    } catch (e) {
      toast("Failed: " + e.message, "error");
    } finally { setBusy(false); }
  };

  return (
    <div className="workspace" style={{ gridTemplateColumns: "1fr" }} data-testid="settings-page">
      <div className="panel" style={{ maxWidth: 720, margin: "0 auto", width: "100%" }}>
        <h2>Account</h2>
        <p>Signed in as <strong>{user?.email}</strong></p>
        <p>
          Current credits:{" "}
          <strong data-testid="credit-balance">
            {user?.unlimited_credits ? "Unlimited (preview)" : (user?.credits ?? 0)}
          </strong>
        </p>

        <div className="divider" />
        {services?.dry_run && (
          <div data-testid="dry-run-banner" role="status"
               style={{ border: "1px solid #fbbf24", borderRadius: 8, padding: "10px 12px",
                        marginBottom: 16, fontSize: 13, lineHeight: 1.6 }}>
            <strong>Demo mode is on.</strong> This workspace cannot reach OpenAI,
            OpenRouter, Stripe or Google (outbound TLS is blocked here), so roasts are
            written and voiced by a local stand-in. Casting, cost, credits, history,
            playback and sharing all work normally, and the audio is a quiet tone
            rather than real speech. Your saved keys are untouched and will be used
            the moment this runs somewhere with network access.
          </div>
        )}
        <ProviderConsole />

        <div className="divider" />
        <h2>Service Configuration</h2>
        {servicesError && <p role="alert" className="text-muted">{servicesError}</p>}
        {!services && !servicesError && <p className="text-muted">Checking service settings…</p>}
        {services && <div data-testid="service-configuration" className="text-muted" style={{ fontSize: 13, lineHeight: 1.8 }}>
          <div><strong>AI writing &amp; OpenAI voices:</strong> {aiStatus}</div>
          <div><strong>ElevenLabs voices:</strong> {elevenStatus}</div>
          <div><strong>Stripe checkout:</strong> {paymentStatus}</div>
          <div><strong>Media storage:</strong> {services.storage_backend === "local" ? "Local workspace" : "Emergent object storage (check credentials)"}</div>
          {user?.is_preview && services.preview_hosted_ai_enabled && <div>Hosted usage is billable; limits are shared across preview accounts and include failed attempts. Up to {services.preview_hosted_daily_voice_limit} uncached voice previews per UTC day are available separately.</div>}
        </div>}
        <p className="text-muted" style={{ fontSize: 12 }}>A saved key is not a live connectivity check. Configure production secrets in the backend environment.</p>

        <div className="divider" />
        <h2>Bring Your Own Keys (BYOK)</h2>
        <p className="text-muted" style={{ fontSize: 13 }}>
          Use your own API keys to bypass the app's quota. Keys are encrypted at rest and never returned to the browser.
        </p>
        {user?.is_preview && <p className="text-muted" style={{ fontSize: 12 }}>
          This is a disposable preview, not a production secret store. Use a restricted key and avoid real customer data.
        </p>}

        <label className="label" style={{ marginTop: 12 }}>
          OpenAI API Key {user?.has_byok_openai && <span className="text-accent">(active)</span>}
        </label>
        <input
          className="input"
          placeholder="sk-..."
          type="password"
          value={openaiKey}
          onChange={(e) => setOpenaiKey(e.target.value)}
          data-testid="openai-key-input"
        />

        <label className="label" style={{ marginTop: 12 }}>
          ElevenLabs API Key {user?.has_byok_elevenlabs && <span className="text-accent">(active)</span>}
        </label>
        <input
          className="input"
          placeholder="xxxx..."
          type="password"
          value={elevenKey}
          onChange={(e) => setElevenKey(e.target.value)}
          data-testid="elevenlabs-key-input"
        />

        <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
          <button className="btn-primary" onClick={save} disabled={busy} data-testid="save-keys-btn">Save Keys</button>
          <button className="btn-secondary" onClick={clearAll} disabled={busy} data-testid="clear-keys-btn">Clear All</button>
        </div>

        <div className="divider" />
        <h2>About Voices</h2>
        <p className="text-muted" style={{ fontSize: 13 }}>
          When ElevenLabs key is set, each persona uses a unique, distinctly-mapped voice.
          Without it, we fall back to OpenAI TTS with 6 spread voices across all 40 personas.
        </p>
      </div>
    </div>
  );
}
