import { useCallback, useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import { useToast } from "@/lib/ToastContext";

/**
 * Owner settings console.
 *
 * Provider credentials are entered here instead of the environment, so a
 * disposable preview can be made fully functional without a redeploy. Saving is
 * deliberately two-phase: every key is checked against its provider first, and
 * only confirmed keys are persisted (to Mongo, encrypted) and mirrored into
 * backend/.env so they survive a restart without ever being committed.
 */

const GROUPS = [
  {
    id: "roast-writer",
    title: "Roast writer (OpenRouter)",
    blurb: "Writes every show. One multimodal call reads the photos and drafts the jokes.",
    fields: ["ROAST_WRITER_PROVIDER", "ROAST_WRITER_PROFILE", "OPENROUTER_API_KEY"],
    models: ["ROAST_FREE_PREMIUM_MODEL", "ROAST_FREE_BACKUP_MODEL"],
  },
  {
    id: "openai",
    title: "OpenAI (voice + backup writer)",
    blurb: "Expressive text-to-speech, and a backup writer when OpenRouter is unavailable.",
    fields: ["OPENAI_API_KEY", "AI_DEFAULT_PROVIDER"],
  },
  {
    id: "elevenlabs",
    title: "ElevenLabs (premium voices)",
    blurb: "Optional. Gives each persona a distinct voice; without it OpenAI voices are used.",
    fields: ["ELEVENLABS_API_KEY"],
  },
  {
    id: "google",
    title: "Google sign-in",
    blurb: "Lets visitors sign in with Google. Copy these from Google Cloud Console → Credentials.",
    fields: ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"],
    note: "Authorised redirect URI must be {origin}/auth-complete.html",
  },
  {
    id: "stripe",
    title: "Stripe (payments)",
    blurb: "Sells credit packs and passes. Webhook secret comes from the endpoint you create.",
    fields: ["STRIPE_API_KEY", "STRIPE_WEBHOOK_SECRET"],
    note: "Webhook endpoint: {origin}/api/payments/webhook",
  },
  {
    id: "models",
    title: "Model choice",
    blurb: "Pin exactly which model runs each show tier. Free models cost nothing; paid models are billed to your OpenRouter account.",
    models: [
      "ROAST_WRITER_MODEL",
      "ROAST_FREE_PREMIUM_MODEL",
      "ROAST_FREE_BACKUP_MODEL",
      "ROAST_PAID_PRIMARY_MODEL",
      "ROAST_PAID_STANDARD_MODEL",
      "ROAST_PAID_BACKUP_MODEL",
    ],
  },
  {
    id: "storage",
    title: "Media storage",
    blurb: "Where portraits, audio and rendered reels are stored.",
    fields: ["STORAGE_BACKEND", "BLOB_READ_WRITE_TOKEN"],
  },
];

const MODEL_PRESETS = {
  ROAST_WRITER_MODEL: ["nvidia/nemotron-3-ultra-550b-a55b:free", "google/gemma-3-27b-it:free", "meta-llama/llama-3.3-70b-instruct:free"],
  ROAST_FREE_PREMIUM_MODEL: ["nvidia/nemotron-3-ultra-550b-a55b:free", "deepseek/deepseek-chat-v3-0324:free", "google/gemini-2.0-flash-exp:free"],
  ROAST_FREE_BACKUP_MODEL: ["nvidia/nemotron-3-ultra-550b-a55b:free", "meta-llama/llama-3.3-70b-instruct:free"],
  ROAST_PAID_PRIMARY_MODEL: ["thedrummer/cydonia-24b-v4.1", "anthropic/claude-sonnet-4.5", "openai/gpt-4.1"],
  ROAST_PAID_STANDARD_MODEL: ["thedrummer/cydonia-24b-v4.1", "openai/gpt-4o", "anthropic/claude-3.5-haiku"],
  ROAST_PAID_BACKUP_MODEL: ["cognitivecomputations/dolphin-mistral-24b-venice-edition", "openai/gpt-4o-mini"],
};

const STATUS_STYLE = {
  valid: { label: "Verified", color: "#4ade80" },
  "shape-ok": { label: "Format OK", color: "#93c5fd" },
  unchecked: { label: "Not confirmed", color: "#fbbf24" },
  invalid: { label: "Rejected", color: "#f87171" },
  pending: { label: "Checking…", color: "#a1a1aa" },
};

function StatusPill({ result }) {
  if (!result) return null;
  const meta = STATUS_STYLE[result.status] || { label: result.status, color: "#a1a1aa" };
  return (
    <span style={{ color: meta.color, fontSize: 12, marginLeft: 8 }} title={result.detail}>
      ● {meta.label}
    </span>
  );
}

export default function ProviderConsole() {
  const { user } = useAuth();
  const { toast } = useToast();
  const [state, setState] = useState(null);
  const [stateError, setStateError] = useState("");
  const [unavailable, setUnavailable] = useState(false);
  const [gate, setGate] = useState(null); // "disabled" | "not-operator" | null
  const [passphrase, setPassphrase] = useState("");
  const [drafts, setDrafts] = useState({});
  const [results, setResults] = useState({});
  const [busy, setBusy] = useState(false);
  const [checked, setChecked] = useState(false);
  const [envStatus, setEnvStatus] = useState(null);

  const origin = typeof window !== "undefined" ? window.location.origin : "";

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/settings/console");
      setState(data);
      setStateError("");
      setUnavailable(false);
      if (data?.unlocked) {
        try {
          const { data: env } = await api.get("/settings/env-status");
          setEnvStatus(env);
        } catch { /* cosmetic only */ }
      }
    } catch (e) {
      const status = e?.response?.status;
      const detail = e?.response?.data?.detail || "";
      if (status === 404) {
        setUnavailable(true);
        setGate("disabled");
      } else if (status === 403) {
        // Only reachable when RUNTIME_SETTINGS_ADMINS narrows access.
        setGate("not-operator");
        setStateError("");
        setUnavailable(false);
        setState({ enabled: true, unlocked: false });
      } else {
        setStateError(detail || "Could not load the settings console.");
      }
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const unlocked = Boolean(state?.unlocked);

  const unlock = async (event) => {
    event.preventDefault();
    if (!passphrase.trim()) return;
    setBusy(true);
    try {
      await api.post("/settings/console/unlock", { passphrase });
      setPassphrase("");
      await load();
      toast("Console unlocked", "success");
    } catch (e) {
      toast(e?.response?.data?.detail || "Could not unlock", "error");
    } finally { setBusy(false); }
  };

  const lock = async () => {
    setBusy(true);
    try {
      await api.post("/settings/console/lock");
      setDrafts({}); setResults({}); setChecked(false);
      await load();
    } catch (e) {
      toast(e?.response?.data?.detail || "Could not lock", "error");
    } finally { setBusy(false); }
  };

  const collected = useMemo(() => {
    const out = {};
    Object.entries(drafts).forEach(([key, value]) => {
      if (value !== undefined && value !== null && String(value).trim()) out[key] = String(value).trim();
    });
    return out;
  }, [drafts]);

  const setDraft = (key, value) => {
    setDrafts((prev) => ({ ...prev, [key]: value }));
    setResults((prev) => { const next = { ...prev }; delete next[key]; return next; });
    setChecked(false);
  };

  const checkKeys = async () => {
    if (!Object.keys(collected).length) { toast("Enter a value first", "info"); return; }
    setBusy(true);
    setChecked(false);
    setResults((prev) => {
      const next = { ...prev };
      Object.keys(collected).forEach((k) => { next[k] = { status: "pending", detail: "Checking with the provider…" }; });
      return next;
    });
    try {
      const { data } = await api.post("/settings/console/validate", { keys: collected });
      const merged = { ...results };
      Object.entries(data?.results || {}).forEach(([k, v]) => { merged[k] = v; });
      setResults(merged);
      setChecked(true);
      if (data?.rejected?.length) toast(`Rejected: ${data.rejected.join(", ")}`, "error");
      else {
        const unconfirmed = Object.values(data?.results || {}).filter((r) => r.status === "unchecked").length;
        toast(unconfirmed ? "Keys look fine, but could not be confirmed offline" : "All keys verified", "success");
      }
    } catch (e) {
      toast(e?.response?.data?.detail?.message || "Could not check keys", "error");
    } finally { setBusy(false); }
  };

  const save = async () => {
    if (!Object.keys(collected).length) { toast("Nothing to save yet", "info"); return; }
    setBusy(true);
    try {
      const { data } = await api.put("/settings/console", { keys: collected, mode: "apply", persist_env: true });
      setDrafts({}); setResults({}); setChecked(false);
      if (data) setState((prev) => ({ ...prev, ...data }));
      const extra = data?.env_written?.length
        ? ` and written to ${data.env_file}` : "";
      toast(`Saved${extra}`, "success");
      if (data?.env_error) toast(data.env_error, "error");
      await load();
    } catch (e) {
      const detail = e?.response?.data?.detail;
      toast(typeof detail === "string" ? detail : (detail?.message || "Could not save"), "error");
      if (detail?.results) setResults((prev) => ({ ...prev, ...detail.results }));
    } finally { setBusy(false); }
  };

  const clearOne = async (key) => {
    if (!window.confirm(`Clear the saved value for ${key}?`)) return;
    setBusy(true);
    try {
      await api.delete(`/settings/console?scope=${encodeURIComponent(key)}`);
      await load();
      toast(`Cleared ${key}`, "success");
    } catch (e) {
      toast(e?.response?.data?.detail || "Could not clear", "error");
    } finally { setBusy(false); }
  };

  if (gate === "not-operator" && !state?.unlocked) {
    return (
      <div data-testid="provider-console-gated">
        <h2>Connect your services</h2>
        <p className="text-muted" style={{ fontSize: 13 }}>
          This panel is limited to specific operator accounts on this server
          (<code>RUNTIME_SETTINGS_ADMINS</code>). Ask the owner to add your email,
          or remove that setting to allow any signed-in account.
        </p>
      </div>
    );
  }

  if (unavailable) {
    return (
      <p className="text-muted" style={{ fontSize: 13 }}>
        The owner settings console is not enabled on this server. Set
        <code> ALLOW_RUNTIME_SETTINGS=true </code> and
        <code> RUNTIME_SETTINGS_PASSPHRASE </code> to turn it on.
      </p>
    );
  }

  const field = (key) => state?.secrets?.[key] || state?.settings?.[key] || null;
  const isSecret = (key) => Boolean(state?.secrets?.[key]);

  const renderField = (key) => {
    const meta = field(key);
    if (!meta) return null;
    const label = meta.label || key;
    const configuredNow = meta.configured ?? Boolean(meta.value);
    const source = meta.source;

    if (!meta.editable) {
      return (
        <div key={key} style={{ marginBottom: 12 }}>
          <label className="label">{label}</label>
          <p className="text-muted" style={{ fontSize: 12, margin: 0 }} data-testid={`locked-${key}`}>
            Set by the server environment{meta.value ? ` (${meta.value})` : ""}. Remove it from the
            environment to manage it here.
          </p>
        </div>
      );
    }

    if (!isSecret(key)) {
      // Non-secret setting: a select when the backend enumerates choices,
      // otherwise a free-text model ID box.
      const choices = meta.choices || [];
      return (
        <div key={key} style={{ marginBottom: 12 }}>
          <label className="label" htmlFor={`setting-${key}`}>{label}</label>
          {choices.length ? (
            <select
              id={`setting-${key}`}
              className="input"
              value={drafts[key] ?? meta.value ?? ""}
              onChange={(e) => setDraft(key, e.target.value)}
              data-testid={`setting-select-${key}`}
            >
              <option value="">(leave unchanged)</option>
              {choices.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          ) : (
            <>
              <input
                id={`setting-${key}`}
                className="input"
                list={`presets-${key}`}
                placeholder={meta.value || "vendor/model"}
                value={drafts[key] ?? ""}
                onChange={(e) => setDraft(key, e.target.value)}
                data-testid={`setting-input-${key}`}
              />
              <datalist id={`presets-${key}`}>
                {(MODEL_PRESETS[key] || []).map((m) => <option key={m} value={m} />)}
              </datalist>
            </>
          )}
          {meta.value && <p className="text-muted" style={{ fontSize: 11, margin: "2px 0 0" }}>current: {meta.value}</p>}
        </div>
      );
    }

    return (
      <div key={key} style={{ marginBottom: 12 }}>
        <label className="label" htmlFor={`secret-${key}`}>
          {label}
          {configuredNow ? (
            <span className="text-accent"> ({source === "environment" ? "environment" : `saved ${meta.hint || ""}`})</span>
          ) : <span className="text-muted"> (not set)</span>}
          <StatusPill result={results[key]} />
        </label>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            id={`secret-${key}`}
            className="input"
            type="password"
            autoComplete="off"
            placeholder={configuredNow ? "Enter a new value to replace" : "Paste here"}
            value={drafts[key] ?? ""}
            onChange={(e) => setDraft(key, e.target.value)}
            data-testid={`secret-input-${key}`}
          />
          {source === "console" && (
            <button className="btn-secondary" type="button" disabled={busy}
                    onClick={() => clearOne(key)} data-testid={`secret-clear-${key}`}>Clear</button>
          )}
        </div>
        {results[key]?.detail && (
          <p className="text-muted" style={{ fontSize: 11, margin: "2px 0 0" }}>{results[key].detail}</p>
        )}
      </div>
    );
  };

  return (
    <div data-testid="provider-console">
      <h2>Connect your services</h2>
      <p className="text-muted" style={{ fontSize: 13 }}>
        Enter the keys this app needs. Every key is checked with its provider before it is
        saved, then stored encrypted <em>and</em> written to <code>backend/.env</code> so it
        survives a restart. That file is gitignored, so nothing leaks into the repository.
      </p>

      {stateError && <p role="alert" className="text-muted">{stateError}</p>}
      {!state && !stateError && <p className="text-muted">Reading current configuration…</p>}

      {state && !unlocked && (
        <form onSubmit={unlock} style={{ marginTop: 12 }}>
          <p className="text-muted" style={{ fontSize: 13 }}>
            Enter the console passphrase to unlock. On this preview workspace the
            passphrase is <code data-testid="console-passphrase-hint">roastbox</code>.
          </p>
          <input
            className="input" type="password" placeholder="Console passphrase"
            value={passphrase} onChange={(e) => setPassphrase(e.target.value)}
            data-testid="console-passphrase" autoComplete="off"
          />
          <button className="btn-primary" type="submit" disabled={busy || !passphrase.trim()}
                  style={{ marginTop: 10 }} data-testid="console-unlock">Unlock console</button>
        </form>
      )}

      {state && unlocked && (
        <div style={{ marginTop: 12 }}>
          <p className="text-muted" style={{ fontSize: 12 }} data-testid="console-unlocked-note">
            Unlocked until {new Date(state.unlocked_until).toLocaleTimeString()} ·{" "}
            {state.unlimited_credits ? "Unlimited credits active" : "Normal credit billing applies"}
            {envStatus && (
              <> · <code>{envStatus.file}</code>{" "}
                <span style={{ color: envStatus.gitignored ? "#4ade80" : "#f87171" }}>
                  {envStatus.gitignored ? "gitignored" : "NOT gitignored"}
                </span>
              </>
            )}
          </p>

          {GROUPS.map((group) => {
            const keys = [...(group.fields || []), ...(group.models || [])];
            const present = keys.filter((k) => field(k));
            if (!present.length) return null;
            return (
              <section key={group.id} style={{ marginTop: 20 }} data-testid={`group-${group.id}`}>
                <h3 style={{ marginBottom: 2 }}>{group.title}</h3>
                <p className="text-muted" style={{ fontSize: 12, marginTop: 0 }}>{group.blurb}</p>
                {group.note && (
                  <p className="text-muted" style={{ fontSize: 11 }}>
                    {group.note.replace("{origin}", origin)}
                  </p>
                )}
                {present.map(renderField)}
              </section>
            );
          })}

          <div style={{ display: "flex", gap: 10, marginTop: 20, flexWrap: "wrap" }}>
            <button className="btn-secondary" onClick={checkKeys}
                    disabled={busy || !Object.keys(collected).length} data-testid="console-check">
              Check keys
            </button>
            <button className="btn-primary" onClick={save}
                    disabled={busy || !Object.keys(collected).length} data-testid="console-save">
              Verify &amp; save
            </button>
            <button className="btn-secondary" onClick={lock} disabled={busy} data-testid="console-lock">
              Lock console
            </button>
          </div>
          {checked && (
            <p className="text-muted" style={{ fontSize: 12, marginTop: 8 }} data-testid="check-summary">
              Checked. "Not confirmed" means the provider could not be reached from this
              environment — the key is saved but unverified, so test it once in the Studio.
            </p>
          )}
          <p className="text-muted" style={{ fontSize: 12, marginTop: 10 }}>
            Saving writes real credentials to <code>backend/.env</code>. That path is added to
            <code> .gitignore</code> automatically so it stays in this workspace only.
          </p>
        </div>
      )}
    </div>
  );
}
