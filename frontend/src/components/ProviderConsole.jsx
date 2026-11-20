import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import { useToast } from "@/lib/ToastContext";

/**
 * Owner settings console.
 *
 * Provider credentials are entered here instead of the environment, so a
 * disposable preview can be made fully functional without a redeploy. The
 * backend never returns a stored secret, only whether one is configured and
 * where it came from; the passphrase unlock is a server-side grant.
 */
export default function ProviderConsole() {
  const { user } = useAuth();
  const { toast } = useToast();
  const [state, setState] = useState(null);
  const [stateError, setStateError] = useState("");
  const [unavailable, setUnavailable] = useState(false);
  const [passphrase, setPassphrase] = useState("");
  const [drafts, setDrafts] = useState({});
  const [settingDrafts, setSettingDrafts] = useState({});
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/settings/console");
      setState(data);
      setStateError("");
      setUnavailable(false);
    } catch (e) {
      if (e?.response?.status === 404) {
        setUnavailable(true);
      } else {
        setStateError(e?.response?.data?.detail || "Could not load the settings console.");
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
      toast("Settings console unlocked", "success");
    } catch (e) {
      toast(e?.response?.data?.detail || "Could not unlock", "error");
    } finally {
      setBusy(false);
    }
  };

  const lock = async () => {
    setBusy(true);
    try {
      await api.post("/settings/console/lock");
      setDrafts({});
      setSettingDrafts({});
      await load();
    } catch (e) {
      toast(e?.response?.data?.detail || "Could not lock", "error");
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    const keys = {};
    Object.entries(drafts).forEach(([key, value]) => {
      if (value !== undefined && value !== null && String(value).trim()) keys[key] = value;
    });
    Object.entries(settingDrafts).forEach(([key, value]) => {
      if (value) keys[key] = value;
    });
    if (!Object.keys(keys).length) {
      toast("Nothing to save yet", "info");
      return;
    }
    setBusy(true);
    try {
      const { data } = await api.put("/settings/console", { keys });
      setDrafts({});
      setSettingDrafts({});
      if (data) setState((prev) => ({ ...prev, ...data }));
      toast(`Saved: ${(data?.changed || []).join(", ")}`, "success");
      await load();
    } catch (e) {
      toast(e?.response?.data?.detail || "Could not save", "error");
    } finally {
      setBusy(false);
    }
  };

  const clearOne = async (key) => {
    if (!window.confirm(`Clear the console-stored value for ${key}?`)) return;
    setBusy(true);
    try {
      await api.delete(`/settings/console?scope=${encodeURIComponent(key)}`);
      await load();
      toast(`Cleared ${key}`, "success");
    } catch (e) {
      toast(e?.response?.data?.detail || "Could not clear", "error");
    } finally {
      setBusy(false);
    }
  };

  if (unavailable) {
    return (
      <p className="text-muted" style={{ fontSize: 13 }}>
        The owner settings console is not enabled on this server. Set
        <code> ALLOW_RUNTIME_SETTINGS=true </code> and
        <code> RUNTIME_SETTINGS_PASSPHRASE </code> in the backend environment to turn it on.
      </p>
    );
  }

  return (
    <div data-testid="provider-console">
      <h2>Connect your services</h2>
      <p className="text-muted" style={{ fontSize: 13 }}>
        Enter the keys this app needs. Values are encrypted at rest and never sent back to the
        browser; a key you set here takes effect on the next request, with no restart.
      </p>

      {stateError && <p role="alert" className="text-muted">{stateError}</p>}
      {!state && !stateError && <p className="text-muted">Reading current configuration…</p>}

      {state && !unlocked && (
        <form onSubmit={unlock} style={{ marginTop: 12 }}>
          <p className="text-muted" style={{ fontSize: 13 }}>
            This console is locked. Enter the passphrase configured for this preview.
          </p>
          <input
            className="input"
            type="password"
            placeholder="Console passphrase"
            value={passphrase}
            onChange={(e) => setPassphrase(e.target.value)}
            data-testid="console-passphrase"
            autoComplete="off"
          />
          <button className="btn-primary" type="submit" disabled={busy || !passphrase.trim()}
                  style={{ marginTop: 10 }} data-testid="console-unlock">
            Unlock console
          </button>
        </form>
      )}

      {state && unlocked && (
        <div style={{ marginTop: 12 }}>
          <p className="text-muted" style={{ fontSize: 12 }} data-testid="console-unlocked-note">
            Unlocked until {new Date(state.unlocked_until).toLocaleTimeString()} ·{" "}
            {state.unlimited_credits
              ? "Unlimited credits active for this preview account"
              : "Normal credit billing applies"}
          </p>

          <h3 style={{ marginTop: 18 }}>API keys &amp; secrets</h3>
          {Object.entries(state.secrets || {}).map(([key, meta]) => (
            <div key={key} style={{ marginBottom: 12 }}>
              <label className="label" htmlFor={`secret-${key}`}>
                {meta.label}{" "}
                {meta.configured && (
                  <span className="text-accent">
                    ({meta.source === "environment" ? "set by environment" : `saved ${meta.hint || ""}`})
                  </span>
                )}
              </label>
              {meta.editable ? (
                <div style={{ display: "flex", gap: 8 }}>
                  <input
                    id={`secret-${key}`}
                    className="input"
                    type="password"
                    placeholder={meta.configured ? "Saved — enter a new value to replace" : "Not set"}
                    value={drafts[key] ?? ""}
                    onChange={(e) => setDrafts((prev) => ({ ...prev, [key]: e.target.value }))}
                    data-testid={`secret-input-${key}`}
                    autoComplete="off"
                  />
                  {meta.source === "console" && (
                    <button className="btn-secondary" type="button" disabled={busy}
                            onClick={() => clearOne(key)} data-testid={`secret-clear-${key}`}>
                      Clear
                    </button>
                  )}
                </div>
              ) : (
                <p className="text-muted" style={{ fontSize: 12, margin: 0 }}>
                  Managed by the server environment. Change it there, or remove it from the
                  environment to manage it here.
                </p>
              )}
            </div>
          ))}

          <h3 style={{ marginTop: 18 }}>Service switches</h3>
          {Object.entries(state.settings || {}).map(([key, meta]) => (
            <div key={key} style={{ marginBottom: 12 }}>
              <label className="label" htmlFor={`setting-${key}`}>
                {meta.label}{" "}
                {meta.source === "environment" && <span className="text-accent">(set by environment)</span>}
              </label>
              {meta.editable ? (
                <select
                  id={`setting-${key}`}
                  className="input"
                  value={settingDrafts[key] ?? meta.value ?? ""}
                  onChange={(e) => setSettingDrafts((prev) => ({ ...prev, [key]: e.target.value }))}
                  data-testid={`setting-select-${key}`}
                >
                  <option value="">(leave unchanged)</option>
                  {(meta.choices || []).map((choice) => (
                    <option key={choice} value={choice}>{choice}</option>
                  ))}
                </select>
              ) : (
                <p className="text-muted" style={{ fontSize: 12, margin: 0 }}>{meta.value}</p>
              )}
            </div>
          ))}

          <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
            <button className="btn-primary" onClick={save} disabled={busy} data-testid="console-save">
              Save settings
            </button>
            <button className="btn-secondary" onClick={lock} disabled={busy} data-testid="console-lock">
              Lock console
            </button>
          </div>
          <p className="text-muted" style={{ fontSize: 12, marginTop: 10 }}>
            A saved key is not a live connectivity check. Use it once from the Studio to confirm it works.
          </p>
        </div>
      )}
    </div>
  );
}
