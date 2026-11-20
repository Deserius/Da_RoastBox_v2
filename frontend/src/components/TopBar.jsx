import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/lib/AuthContext";
import api, { API_BASE } from "@/lib/api";
import { useState } from "react";
import AccountMenu from "@/components/AccountMenu";

export default function TopBar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [downloading, setDownloading] = useState(false);

  const onDownload = () => {
    // The Emergent preview iframe sandboxes blob-based downloads. Opening the
    // backend endpoint in a new tab bypasses the sandbox — the browser handles
    // Content-Disposition: attachment natively and saves the zip to disk.
    const url = `${API_BASE}/download/source.zip`;
    setDownloading(true);
    const win = window.open(url, "_blank", "noopener");
    if (!win) {
      // Popup blocked — fall back to same-tab navigation (browser still triggers download
      // due to Content-Disposition; current SPA route is preserved by back nav).
      window.location.href = url;
    }
    // Reset state shortly after — there's no reliable "download finished" event for cross-origin.
    setTimeout(() => setDownloading(false), 1500);
  };

  return (
    <header className="topbar">
      <Link to="/studio" className="brand" data-testid="brand-link">
        <span className="brand-flame">🔥</span>
        <span>DA ROASTBOX!</span>
      </Link>
      <div className="topbar-actions">
        <span className="credit-pill" data-testid="credit-pill">
          🔥 {user?.credits ?? 0} Credits{user?.is_preview ? " · Preview" : ""}
        </span>
        <button className="btn-ghost" onClick={() => navigate("/roasters")} data-testid="nav-roasters-btn">Roasters</button>
        <button className="btn-ghost" onClick={() => navigate("/battle")} data-testid="nav-battle-btn">🥊 Battle</button>
        <button className="btn-ghost" onClick={() => navigate("/credits")} data-testid="nav-credits-btn">Buy Credits</button>
        <button className="btn-ghost" onClick={() => navigate("/settings")} data-testid="nav-settings-btn">Settings</button>
        {process.env.REACT_APP_SOURCE_DOWNLOAD_ENABLED === "true" && (
          <button className="btn-ghost" onClick={onDownload} disabled={downloading} data-testid="download-source-btn">
            {downloading ? "Zipping…" : "⬇ Source.zip"}
          </button>
        )}
        <button className="btn-ghost" onClick={logout} data-testid="logout-btn">Logout</button>
      </div>
      <AccountMenu user={user} logout={logout} onDownload={onDownload} downloading={downloading} />
    </header>
  );
}
