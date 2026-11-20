import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import { useToast } from "@/lib/ToastContext";

const PersonaFavoritesContext = createContext(null);

// Favorites belong to the signed-in account, not the current browser or page.
export const PersonaFavoritesProvider = ({ children }) => {
  const { user } = useAuth();
  const { toast } = useToast();
  const [ids, setIds] = useState([]);
  const [pending, setPending] = useState([]);
  const [status, setStatus] = useState("loading");
  const [reload, setReload] = useState(0);
  const latest = useRef(new Set());
  const pendingRef = useRef(new Set());
  const generation = useRef(0);
  const userId = user?.id || null;

  useEffect(() => {
    const version = ++generation.current;
    const abort = new AbortController();
    latest.current = new Set();
    pendingRef.current = new Set();
    setIds([]);
    setPending([]);
    if (!userId) {
      setStatus("signedout");
      return () => abort.abort();
    }
    setStatus("loading");
    api.get("/personas/favorites", { signal: abort.signal }).then(({ data }) => {
      if (generation.current !== version) return;
      latest.current = new Set(Array.isArray(data.favorites) ? data.favorites : []);
      setIds([...latest.current]);
      setStatus("ready");
    }).catch(() => {
      if (!abort.signal.aborted && generation.current === version) setStatus("error");
    });
    return () => abort.abort();
  }, [userId, reload]);

  const toggle = useCallback(async (id) => {
    if (!userId || status !== "ready" || pendingRef.current.has(id)) return;
    const version = generation.current;
    const wasFavorite = latest.current.has(id);
    const next = new Set(latest.current);
    if (wasFavorite) next.delete(id); else next.add(id);
    latest.current = next;
    setIds([...next]);
    pendingRef.current.add(id);
    setPending([...pendingRef.current]);
    try {
      if (wasFavorite) await api.delete(`/personas/favorites/${encodeURIComponent(id)}`);
      else await api.put(`/personas/favorites/${encodeURIComponent(id)}`);
    } catch {
      if (generation.current === version) {
        // Roll back only this card, preserving any other successful changes.
        const rollback = new Set(latest.current);
        if (wasFavorite) rollback.add(id); else rollback.delete(id);
        latest.current = rollback;
        setIds([...rollback]);
        toast("Couldn't save that favorite. Please try again.", "error");
      }
    } finally {
      if (generation.current === version) {
        pendingRef.current.delete(id);
        setPending([...pendingRef.current]);
      }
    }
  }, [status, toast, userId]);

  const favoriteSet = useMemo(() => new Set(ids), [ids]);
  const pendingSet = useMemo(() => new Set(pending), [pending]);
  const value = useMemo(() => ({ favoriteSet, pendingSet, status, toggle, retry: () => setReload((n) => n + 1) }),
    [favoriteSet, pendingSet, status, toggle]);
  return <PersonaFavoritesContext.Provider value={value}>{children}</PersonaFavoritesContext.Provider>;
};

export const usePersonaFavorites = () => useContext(PersonaFavoritesContext);
