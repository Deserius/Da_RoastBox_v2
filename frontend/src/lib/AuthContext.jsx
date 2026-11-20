import { createContext, useContext, useState, useEffect, useCallback, useRef } from "react";
import api from "@/lib/api";
import { activateShowDrafts, clearShowDrafts } from "@/lib/showDraft";
import { getSessionToken, setSessionToken, clearSessionToken } from "@/lib/sessionStore";

const AuthContext = createContext(null);
const AUTH_STATE_KEY = "roastbox_google_auth_state";
const AUTH_RESULT_KEY = "roastbox_google_auth_result";
const AUTH_MESSAGE = "roastbox-google-auth-result";
// How long a sign-in attempt's state token stays valid for.
const AUTH_MAX_AGE_MS = 5 * 60 * 1000;

function newState() {
  if (!window.crypto?.getRandomValues) throw new Error("secure_context_required");
  const bytes = window.crypto.getRandomValues(new Uint8Array(32));
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function signInError(error) {
  const status = error?.response?.status;
  if (status === 503) {
    return error?.response?.data?.detail
      || "Google sign-in isn't set up yet. Add a Google OAuth client ID and secret in Settings.";
  }
  if (status === 401 || status === 400 || status === 422) {
    return "Your Google sign-in expired or could not be verified. Please try again.";
  }
  if (status === 429) return "Too many sign-in attempts. Please wait and try again.";
  if (status >= 500) return "The sign-in service is temporarily unavailable. Please try again.";
  return "We couldn't finish signing you in. Check your connection and try again.";
}

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loginBusy, setLoginBusy] = useState(false);
  const [loginError, setLoginError] = useState("");
  const [googleConfig, setGoogleConfig] = useState(null);
  const popupAttempt = useRef(null);
  const authRequestVersion = useRef(0);

  // Fetched once up front (not inside login()) so clicking "Continue with
  // Google" can call window.open synchronously in the same click - any
  // await beforehand and most browsers silently block the popup.
  useEffect(() => {
    let cancelled = false;
    api.get("/auth/google/config").then(({ data }) => {
      if (!cancelled) setGoogleConfig(data);
    }).catch(() => {
      if (!cancelled) setGoogleConfig({ configured: false });
    });
    return () => { cancelled = true; };
  }, []);

  const fetchMe = useCallback(async ({ throwOnFailure = false } = {}) => {
    // A slow anonymous /me response must never erase a newer login or sign-out.
    const requestVersion = ++authRequestVersion.current;
    const tokenAtStart = getSessionToken();
    if (window.location.pathname.startsWith("/r/") && !tokenAtStart) {
      if (requestVersion === authRequestVersion.current) {
        setUser(null);
        setLoading(false);
      }
      return null;
    }
    try {
      const { data } = await api.get("/auth/me", { timeout: 10000 });
      if (requestVersion !== authRequestVersion.current) return null;
      activateShowDrafts(data?.id);
      setUser(data);
      return data;
    } catch (e) {
      if (requestVersion === authRequestVersion.current) {
        if (e?.response?.status === 401) { clearSessionToken(tokenAtStart); clearShowDrafts(); }
        else if (!throwOnFailure) setLoginError("The app couldn't reach its server. Check your connection and try again.");
        setUser(null);
      }
      if (throwOnFailure) throw e;
      return null;
    } finally {
      if (requestVersion === authRequestVersion.current) setLoading(false);
    }
  }, []);

  const finishSignIn = useCallback(async (code) => {
    let tokenStored = false;
    try {
      const redirectUri = new URL("/auth-complete.html", window.location.origin).toString();
      const { data } = await api.post("/auth/google/exchange", { code, redirect_uri: redirectUri });
      if (typeof data?.session_token !== "string" || !data.session_token) throw new Error("incomplete_session");
      // The app's bearer token also works when a browser blocks third-party cookies
      // in an embedded preview. It is a locally issued token, not a Google credential.
      setSessionToken(data.session_token);
      tokenStored = data.session_token;
      const currentUser = await fetchMe({ throwOnFailure: true });
      if (!currentUser) throw new Error("session_not_available");
      setLoginError("");
      return true;
    } catch (error) {
      if (tokenStored) clearSessionToken(tokenStored);
      setUser(null);
      setLoginError(signInError(error));
      setLoading(false);
      return false;
    }
  }, [fetchMe]);

  // For a regular top-level redirect, the minimal callback page removes the
  // provider fragment before the main app (and its third-party scripts) loads.
  const initialized = useRef(false);
  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    (async () => {
      if (window.location.pathname === "/auth/callback") {
        // Old, unbound callback links cannot be safely accepted. Ask the user to
        // start a fresh login rather than silently signing into the wrong account.
        if (window.location.hash) {
          window.history.replaceState(null, "", window.location.pathname);
          setLoginError("This sign-in link has expired. Please start again.");
          setLoading(false);
          return;
        }
        let result, expected;
        try {
          result = JSON.parse(sessionStorage.getItem(AUTH_RESULT_KEY) || "null");
          expected = JSON.parse(sessionStorage.getItem(AUTH_STATE_KEY) || "null");
          sessionStorage.removeItem(AUTH_RESULT_KEY);
          sessionStorage.removeItem(AUTH_STATE_KEY);
        } catch {
          setLoginError("Your browser couldn't complete sign-in. Please try again.");
          setLoading(false);
          return;
        }
        const age = Date.now() - (expected?.createdAt || 0);
        if (!result || !expected || result.type !== AUTH_MESSAGE || result.state !== expected.state || age < 0 || age > AUTH_MAX_AGE_MS) {
          setLoginError("This sign-in attempt could not be verified. Please try again.");
          setLoading(false);
          return;
        }
        if (result.error || !result.code) {
          setLoginError("Google sign-in was canceled or didn't finish. Please try again.");
          setLoading(false);
          return;
        }
        await finishSignIn(result.code);
        return;
      }
      await fetchMe();
    })();
  }, [fetchMe, finishSignIn]);

  // Google's account page refuses to render in an iframe. In embedded previews,
  // use a top-level popup and accept its result only from that exact window,
  // this app's origin, and the fresh random state for the current attempt.
  useEffect(() => {
    const receive = async (event) => {
      const attempt = popupAttempt.current;
      if (!attempt || event.origin !== window.location.origin || event.source !== attempt.popup || event.data?.type !== AUTH_MESSAGE) return;
      window.clearInterval(attempt.timer);
      window.clearTimeout(attempt.closeTimer);
      popupAttempt.current = null;
      if (event.data.state !== attempt.state || Date.now() - attempt.createdAt > AUTH_MAX_AGE_MS) {
        setLoginBusy(false);
        setLoginError("This sign-in attempt could not be verified. Please try again.");
        return;
      }
      if (event.data.error || !event.data.code) {
        setLoginBusy(false);
        setLoginError("Google sign-in was canceled or didn't finish. Please try again.");
        return;
      }
      await finishSignIn(event.data.code);
      setLoginBusy(false);
    };
    window.addEventListener("message", receive);
    return () => {
      window.removeEventListener("message", receive);
      const attempt = popupAttempt.current;
      if (attempt) {
        window.clearInterval(attempt.timer);
        window.clearTimeout(attempt.closeTimer);
        popupAttempt.current = null;
      }
    };
  }, [finishSignIn]);

  const login = () => {
    if (popupAttempt.current || loginBusy) return;
    setLoginError("");
    if (!googleConfig) {
      setLoginError("Still connecting to the server. Please try again in a moment.");
      return;
    }
    if (!googleConfig.configured || !googleConfig.client_id) {
      setLoginError("Google sign-in isn't set up yet. Add a Google OAuth client ID and secret in Settings.");
      return;
    }
    let state;
    try {
      state = newState();
    } catch {
      setLoginError("Google sign-in requires a secure HTTPS connection. Open the app over HTTPS and try again.");
      return;
    }
    let embedded = true;
    try { embedded = window.self !== window.top; } catch { /* Treat restricted frames as embedded. */ }
    const createdAt = Date.now();
    let redirectMode = !embedded;
    // The popup/redirect mode travels inside Google's own opaque "state"
    // value: the redirect_uri sent to Google must exactly match what's
    // registered in Google Cloud Console, so it cannot carry extra query
    // params of our own.
    if (redirectMode) {
      try {
        sessionStorage.removeItem(AUTH_RESULT_KEY);
        sessionStorage.setItem(AUTH_STATE_KEY, JSON.stringify({ state: `${state}.redirect`, createdAt }));
      } catch {
        // A popup keeps state in memory if this browser blocks sessionStorage.
        redirectMode = false;
      }
    }
    const fullState = `${state}.${redirectMode ? "redirect" : "popup"}`;
    const redirectUri = new URL("/auth-complete.html", window.location.origin).toString();
    const authUrl = new URL(googleConfig.auth_url || "https://accounts.google.com/o/oauth2/v2/auth");
    authUrl.searchParams.set("client_id", googleConfig.client_id);
    authUrl.searchParams.set("redirect_uri", redirectUri);
    authUrl.searchParams.set("response_type", "code");
    authUrl.searchParams.set("scope", "openid email profile");
    authUrl.searchParams.set("access_type", "online");
    authUrl.searchParams.set("prompt", "select_account");
    authUrl.searchParams.set("state", fullState);
    const providerUrl = authUrl.toString();

    if (redirectMode) {
      window.location.assign(providerUrl);
      return;
    }

    let popup;
    try { popup = window.open(providerUrl, "_blank", "popup,width=520,height=720"); } catch { popup = null; }
    if (!popup) {
      setLoginError("Your browser blocked the Google sign-in window. Allow pop-ups, or open this app in a new tab and try again.");
      return;
    }
    const attempt = { popup, state: fullState, createdAt, timer: null, closeTimer: null };
    popupAttempt.current = attempt;
    setLoginBusy(true);
    attempt.timer = window.setInterval(() => {
      if (popupAttempt.current !== attempt) return;
      if (Date.now() - createdAt > AUTH_MAX_AGE_MS) {
        window.clearInterval(attempt.timer);
        popupAttempt.current = null;
        try { popup.close(); } catch { /* The browser may have closed it already. */ }
        setLoginBusy(false);
        setLoginError("Google sign-in timed out. Please try again.");
        return;
      }
      let closed = false;
      try { closed = popup.closed; } catch { /* A cross-origin popup can remain open. */ }
      if (closed && !attempt.closeTimer) {
        // postMessage is asynchronous; allow a final message to arrive after close.
        window.clearInterval(attempt.timer);
        attempt.closeTimer = window.setTimeout(() => {
          if (popupAttempt.current !== attempt) return;
          popupAttempt.current = null;
          setLoginBusy(false);
          setLoginError("The Google sign-in window closed before sign-in finished. Please try again.");
        }, 1000);
      }
    }, 500);
  };

  const cancelLogin = () => {
    const attempt = popupAttempt.current;
    if (attempt) {
      window.clearInterval(attempt.timer);
      window.clearTimeout(attempt.closeTimer);
      popupAttempt.current = null;
      try { attempt.popup.close(); } catch { /* Ignore a previously closed window. */ }
    }
    setLoginBusy(false);
    setLoginError("");
  };

  const previewLogin = async () => {
    setLoginError("");
    const { data } = await api.post("/auth/preview-login", {}, { timeout: 15000 });
    if (typeof data?.session_token !== "string" || !data.session_token) {
      throw new Error("The preview server returned an incomplete session. Please try again.");
    }
    const token = data.session_token;
    setSessionToken(token);
    try {
      const currentUser = await fetchMe({ throwOnFailure: true });
      if (!currentUser) throw new Error("The preview session couldn't be verified. Please try again.");
      return currentUser;
    } catch (error) {
      clearSessionToken(token);
      throw error;
    }
  };

  const emailLogin = async (email, password) => {
    setLoginError("");
    const { data } = await api.post("/auth/email/login", { email, password }, { timeout: 15000 });
    if (typeof data?.session_token !== "string" || !data.session_token) throw new Error("incomplete_session");
    const token = data.session_token;
    setSessionToken(token);
    try {
      const currentUser = await fetchMe({ throwOnFailure: true });
      if (!currentUser) throw new Error("session_not_available");
      return currentUser;
    } catch (error) {
      clearSessionToken(token);
      throw error;
    }
  };

  const logout = async () => {
    cancelLogin();
    // Invalidate any /me request that was already in flight.
    authRequestVersion.current += 1;
    try { await api.post("/auth/logout", {}, { timeout: 10000 }); } catch {}
    clearSessionToken();
    clearShowDrafts();
    setUser(null);
    setLoading(false);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, loginBusy, loginError, cancelLogin, previewLogin, emailLogin, logout, refresh: fetchMe, setUser }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
