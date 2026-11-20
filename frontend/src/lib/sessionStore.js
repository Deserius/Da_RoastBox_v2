// Session storage can be unavailable in private browsing or embedded previews.
// Keep an in-memory copy so navigation still works for the current tab.
const KEY = "roastbox_token";
let memoryToken = null;
let memoryIsAuthoritative = false;

export function getSessionToken() {
  if (memoryIsAuthoritative) return memoryToken;
  try {
    memoryToken = window.localStorage.getItem(KEY);
  } catch {
    // The browser may refuse storage entirely. Memory remains usable.
  }
  return memoryToken;
}

export function setSessionToken(token) {
  memoryToken = token || null;
  memoryIsAuthoritative = true;
  try {
    if (memoryToken) window.localStorage.setItem(KEY, memoryToken);
    else window.localStorage.removeItem(KEY);
  } catch {
    // Authentication will continue in memory until this tab is closed.
  }
}

export function clearSessionToken(expectedToken) {
  if (expectedToken !== undefined && getSessionToken() !== expectedToken) return;
  setSessionToken(null);
}

// Sync logins/logouts from another tab when the browser allows shared storage.
if (typeof window !== "undefined") {
  window.addEventListener("storage", (event) => {
    if (event.key === KEY) {
      memoryToken = event.newValue || null;
      memoryIsAuthoritative = true;
    } else if (event.key === null) {
      memoryToken = null;
      memoryIsAuthoritative = true;
    }
  });
}
