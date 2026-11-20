import { useState } from "react";
import api from "@/lib/api";
import { useToast } from "@/lib/ToastContext";

export const ShareButton = ({ roastId }) => {
  const { toast } = useToast();
  const [link, setLink] = useState("");
  const [busy, setBusy] = useState(false);

  const share = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/roast/${roastId}/share`);
      const url = `${window.location.origin}${data.share_path}`;
      setLink(url);
      try {
        await navigator.clipboard.writeText(url);
        toast("Share link copied 🔗", "success");
      } catch {
        toast("Share link ready — copy it below", "success");
      }
    } catch (e) {
      toast("Share failed: " + (e?.response?.data?.detail || e.message), "error");
    } finally {
      setBusy(false);
    }
  };

  if (!roastId) return null;
  return (
    <div className="share-row">
      <button className="btn-secondary" onClick={share} disabled={busy} data-testid="share-roast-btn">
        {busy ? "…" : "🔗 Share"}
      </button>
      {link && (
        <input className="input share-link" readOnly value={link} onFocus={(e) => e.target.select()} data-testid="share-link-input" />
      )}
    </div>
  );
};
