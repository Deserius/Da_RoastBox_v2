import { createContext, useContext, useState } from "react";

// The old splash checkbox was transient. Store an explicit decision only in
// this tab's session so OAuth redirects/reloads do not erase it; there is no
// automatic acceptance, permanent tracking, or server-side age verification.
const KEY = "roastbox_adult_consent_v1";
const ConsentContext = createContext(null);

function initialConsent() {
  try { return sessionStorage.getItem(KEY) === "accepted" ? "accepted" : "pending"; }
  catch { return "pending"; }
}

export function ConsentProvider({ children }) {
  const [status, setStatus] = useState(initialConsent);
  const accept = () => {
    try { sessionStorage.setItem(KEY, "accepted"); } catch { /* Keep the decision in memory. */ }
    setStatus("accepted");
  };
  const decline = () => {
    try { sessionStorage.removeItem(KEY); } catch { /* Storage may be unavailable. */ }
    setStatus("declined");
  };
  const review = () => setStatus("pending");
  return <ConsentContext.Provider value={{ status, accept, decline, review }}>{children}</ConsentContext.Provider>;
}
export const useConsent = () => useContext(ConsentContext);
