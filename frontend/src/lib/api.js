import axios from "axios";
import { getSessionToken } from "@/lib/sessionStore";

const BACKEND_URL = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/$/, "");
export const API_BASE = `${BACKEND_URL}/api`;
export const AUDIO_BASE = BACKEND_URL;

const api = axios.create({ baseURL: API_BASE, withCredentials: true, timeout: 20000 });
let bodyTransport = false;

function tunnelConfig(config, token) {
  const target = new URL(api.getUri(config), window.location.origin);
  const trusted = new URL(API_BASE, window.location.origin);
  if (target.origin !== trusted.origin || !target.pathname.startsWith("/api/")) {
    throw new Error("Invalid API request path");
  }
  const outer = new FormData();
  outer.append("token", token);
  outer.append("method", (config.method || "get").toUpperCase());
  outer.append("path", target.pathname + target.search);
  const data = config.data;
  if (data instanceof FormData) {
    outer.append("kind", "form");
    for (const [name, value] of data.entries()) {
      if (value instanceof Blob) outer.append(`file:${name}`, value, value.name || "upload");
      else outer.append(`field:${name}`, value);
    }
  } else if (data !== undefined && data !== null && data !== "") {
    outer.append("kind", "json");
    outer.append("payload", typeof data === "string" ? data : JSON.stringify(data));
  } else {
    outer.append("kind", "none");
  }
  const headers = axios.AxiosHeaders.from(config.headers || {});
  headers.delete("Authorization");
  headers.delete("X-Roastbox-Session");
  headers.delete("Content-Type");
  return { ...config, method: "post", url: "/session/dispatch", params: undefined,
    data: outer, headers, __tunneled: true, __forceTunnel: false };
}

api.interceptors.request.use((config) => {
  const tok = getSessionToken();
  if (tok) {
    // Public login exchanges must remain direct; the tunnel is only for a
    // session that has already been issued by this app.
    const publicLogin = /^\/auth\/(session|preview-login|email\/(?:status|login|register|verify|forgot|reset))(?:\?|$)/.test(config.url || "");
    if (!config.__tunneled && !publicLogin && (bodyTransport || config.__forceTunnel)) {
      return tunnelConfig(config, tok);
    }
    config.headers.Authorization = `Bearer ${tok}`;
    config.headers["X-Roastbox-Session"] = tok;
  }
  return config;
});

api.interceptors.response.use((response) => response, async (error) => {
  const config = error?.config;
  // Some embedded preview gateways strip *all* auth headers and cookies. Only
  // retry the side-effect-free session check; after it succeeds, subsequent API
  // requests use the body transport. No session token is put in a URL.
  if (error?.response?.status === 401 && config && !config.__tunneled &&
      (config.url || "").split("?")[0] === "/auth/me" && getSessionToken()) {
    const response = await api.request({ ...config, __forceTunnel: true });
    bodyTransport = true;
    return response;
  }
  throw error;
});

export default api;
